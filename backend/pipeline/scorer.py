"""
점수 산출 + 근거 생성 — 파이프라인 ③ 단계
============================================
AnalysisResult(분석기 출력) → ScoreReport(종합 리포트)

역할:
- analyzer.py가 산출한 SCI 점수 + 3축 에너지 + 이슈 목록을 받아
- 인간이 읽을 수 있는 근거 텍스트를 생성하고
- 항목별 개선 제안을 구조화하여
- 대시보드(ScoreGauge, AxisBreakdown) + optimizer.py에 전달

흐름:
  코드 → parser → analyzer → scorer.score() → ScoreReport
                                                  ↓
                                          optimizer.py (STEP 6)
                                          대시보드 렌더링 (STEP 7)
"""
from dataclasses import dataclass, field

from pipeline.analyzer import AnalysisResult
from sci.formula import SCIResult


# ================================================================
# 등급별 설명 + 색상 (대시보드 ScoreGauge 컴포넌트용)
# ================================================================
GRADE_INFO = {
    "A": {
        "label": "매우 효율적",
        "color": "#22c55e",    # green-500
        "description": "에너지 사용이 최적화된 코드입니다.",
        "emoji": "🟢",
    },
    "B": {
        "label": "양호",
        "color": "#84cc16",    # lime-500
        "description": "대체로 효율적이나 소폭 개선 여지가 있습니다.",
        "emoji": "🟡",
    },
    "C": {
        "label": "보통",
        "color": "#eab308",    # yellow-500
        "description": "에너지 비효율 패턴이 일부 존재합니다. 개선을 권장합니다.",
        "emoji": "🟠",
    },
    "D": {
        "label": "개선 필요",
        "color": "#f97316",    # orange-500
        "description": "에너지 비효율이 심각합니다. 즉각적 개선이 필요합니다.",
        "emoji": "🔴",
    },
    "F": {
        "label": "심각한 비효율",
        "color": "#ef4444",    # red-500
        "description": "에너지 소비가 매우 높습니다. 전면적 리팩토링이 필요합니다.",
        "emoji": "⛔",
    },
}


@dataclass
class Finding:
    """단일 분석 발견 사항 — 근거 1건"""
    axis: str               # "compute" | "data" | "token"
    severity: str            # "high" | "medium" | "low" | "info"
    line: int                # 코드 줄 번호
    function_name: str       # 해당 함수명
    problem: str             # 무엇이 문제인가 (한글)
    energy_impact: str       # 에너지 영향도 설명
    suggestion: str          # 개선 제안 (한글)
    estimated_reduction: str # 개선 시 예상 절감 (예: "~90% Token 절감")


@dataclass
class AxisSummary:
    """축별 요약 — 대시보드 AxisBreakdown 컴포넌트용"""
    axis: str                # "compute" | "data" | "token"
    energy_kwh: float        # 에너지 (kWh)
    energy_gco2: float       # 탄소 배출 (gCO2)
    percentage: float        # 전체 대비 비율 (%)
    finding_count: int       # 발견 사항 수
    status: str              # "good" | "warning" | "critical"


@dataclass
class ScoreReport:
    """
    종합 점수 리포트 — optimizer.py와 대시보드의 입력

    이 객체가 GreenPulse 분석의 최종 산출물이다.
    대시보드의 모든 컴포넌트(ScoreGauge, AxisBreakdown, CodeDiff)가
    이 리포트를 기반으로 렌더링된다.
    """
    # SCI 점수 + 등급
    sci_score: float
    grade: str
    grade_label: str         # "매우 효율적", "개선 필요" 등
    grade_color: str         # 대시보드 게이지 색상
    grade_description: str   # 등급 설명 텍스트

    # 3축 에너지 요약
    axis_summaries: list     # AxisSummary 리스트 [compute, data, token]

    # 항목별 발견 사항 (근거)
    findings: list           # Finding 리스트 (severity 높은 순 정렬)

    # 종합 요약 텍스트 (대시보드 상단 표시)
    summary_text: str

    # 통계
    total_functions: int
    total_lines: int
    total_energy_kwh: float
    total_carbon_gco2: float

    # 원본 분석 결과 참조 (optimizer에서 사용)
    analysis_result: AnalysisResult = field(repr=False)


def score(analysis: AnalysisResult) -> ScoreReport:
    """
    분석 결과를 종합 점수 리포트로 변환

    파이프라인 ③ 단계의 핵심 함수.
    analyzer.py의 출력을 인간이 읽을 수 있는 형태로 변환한다.

    Args:
        analysis: analyzer.analyze()의 출력

    Returns:
        ScoreReport — 종합 리포트 (대시보드 + optimizer 입력)
    """
    sci = analysis.sci_result
    eb = analysis.energy_breakdown

    # === 등급 정보 조회 ===
    grade_info = GRADE_INFO.get(sci.grade, GRADE_INFO["F"])

    # === 3축 요약 생성 ===
    axis_summaries = _build_axis_summaries(eb, sci.carbon_intensity, analysis)

    # === 발견 사항(근거) 생성 ===
    findings = _build_findings(analysis)

    # === 종합 요약 텍스트 ===
    summary_text = _build_summary_text(sci, analysis, findings)

    return ScoreReport(
        sci_score=sci.sci_score,
        grade=sci.grade,
        grade_label=grade_info["label"],
        grade_color=grade_info["color"],
        grade_description=grade_info["description"],
        axis_summaries=axis_summaries,
        findings=findings,
        summary_text=summary_text,
        total_functions=analysis.total_functions,
        total_lines=analysis.total_lines,
        total_energy_kwh=eb.total_energy_kwh,
        total_carbon_gco2=sci.total_carbon,
        analysis_result=analysis,
    )


# ================================================================
# 3축 요약 생성
# ================================================================
def _build_axis_summaries(
    eb,
    carbon_intensity: float,
    analysis: AnalysisResult,
) -> list[AxisSummary]:
    """
    Compute / Data / Token 3축 에너지 요약

    각 축의 에너지를 gCO2로 변환하고, 전체 대비 비율을 계산.
    발견 사항 수와 심각도에 따라 status (good/warning/critical) 결정.
    """
    total = eb.total_energy_kwh if eb.total_energy_kwh > 0 else 1e-20

    axes = [
        ("compute", eb.compute_energy_kwh),
        ("data", eb.data_energy_kwh),
        ("token", eb.token_energy_kwh),
    ]

    summaries = []
    for axis_name, energy in axes:
        gco2 = energy * carbon_intensity
        pct = (energy / total) * 100

        # 해당 축의 이슈 수로 status 결정
        axis_issues = [
            i for i in analysis.issues
            if i["type"] == axis_name
        ]
        high_count = sum(1 for i in axis_issues if i["severity"] == "high")

        if high_count >= 1:
            status = "critical"
        elif len(axis_issues) >= 1:
            status = "warning"
        else:
            status = "good"

        summaries.append(AxisSummary(
            axis=axis_name,
            energy_kwh=round(energy, 10),
            energy_gco2=round(gco2, 4),
            percentage=round(pct, 1),
            finding_count=len(axis_issues),
            status=status,
        ))

    return summaries


# ================================================================
# 발견 사항(근거) 생성
# ================================================================
def _build_findings(analysis: AnalysisResult) -> list[Finding]:
    """
    분석기의 이슈 목록 → 인간이 읽을 수 있는 Finding 리스트로 변환

    각 이슈에 대해:
    1. 문제 설명 (무엇이 비효율적인가)
    2. 에너지 영향 (얼마나 에너지를 쓰는가)
    3. 개선 제안 (어떻게 고치는가)
    4. 예상 절감 (고치면 얼마나 절약되는가)
    """
    findings = []

    for func_analysis in analysis.function_analyses:
        for issue in func_analysis.issues:
            finding = _issue_to_finding(issue, func_analysis.name)
            findings.append(finding)

    # severity 우선순위: high → medium → low → info
    severity_order = {"high": 0, "medium": 1, "low": 2, "info": 3}
    findings.sort(key=lambda f: severity_order.get(f.severity, 4))

    return findings


def _issue_to_finding(issue: dict, function_name: str) -> Finding:
    """개별 이슈 → Finding 변환"""
    axis = issue["type"]
    severity = issue["severity"]
    line = issue["line"]
    message = issue["message"]
    suggestion = issue.get("suggestion", "")

    # 축별 에너지 영향 설명 + 예상 절감
    energy_impact, estimated_reduction = _get_impact_and_reduction(
        axis, severity, message
    )

    return Finding(
        axis=axis,
        severity=severity,
        line=line,
        function_name=function_name,
        problem=message,
        energy_impact=energy_impact,
        suggestion=suggestion,
        estimated_reduction=estimated_reduction,
    )


def _get_impact_and_reduction(
    axis: str,
    severity: str,
    message: str,
) -> tuple[str, str]:
    """축 + 심각도에 따른 에너지 영향 설명 + 예상 절감"""

    if axis == "compute":
        if "n^2" in message or "n²" in message:
            return (
                "O(n²) 알고리즘은 입력 크기에 제곱 비례하여 CPU 에너지를 소비합니다.",
                "~90% Compute 절감 (O(n) 변환 시)",
            )
        elif "n^3" in message:
            return (
                "O(n³) 알고리즘은 극도로 높은 CPU 에너지를 소비합니다.",
                "~99% Compute 절감 (O(n log n) 변환 시)",
            )
        else:
            return (
                "높은 복잡도의 코드가 CPU 에너지를 과도하게 소비합니다.",
                "~50% Compute 절감 (로직 단순화 시)",
            )

    elif axis == "data":
        if "N+1" in message:
            return (
                "N+1 쿼리는 데이터 건수만큼 개별 DB 호출을 발생시켜 IO 에너지를 낭비합니다.",
                "~95% Data 절감 (JOIN 1회 쿼리 변환 시)",
            )
        else:
            return (
                "불필요한 DB/네트워크 IO가 에너지를 낭비합니다.",
                "~50% Data 절감 (IO 최적화 시)",
            )

    elif axis == "token":
        if "캐싱 없는" in message or "캐싱 없이" in message:
            return (
                "매 호출마다 LLM API를 실행하여 막대한 토큰 에너지를 소비합니다.",
                "~90% Token 절감 (@lru_cache 적용 시)",
            )
        elif "캐시 데코레이터" in message:
            return (
                "캐시 데코레이터가 적용되어 중복 LLM 호출이 절감됩니다.",
                "이미 적용됨 (TTL/maxsize 최적화 검토)",
            )
        else:
            return (
                "LLM API 호출이 토큰 에너지를 소비합니다.",
                "~50% Token 절감 (호출 빈도 최적화 시)",
            )

    return ("에너지 영향 분석 필요", "개선 효과 추정 필요")


# ================================================================
# 종합 요약 텍스트 생성
# ================================================================
def _build_summary_text(
    sci: SCIResult,
    analysis: AnalysisResult,
    findings: list[Finding],
) -> str:
    """
    대시보드 상단에 표시되는 1~3줄 종합 요약

    예시:
    "SCI 460.1 (F등급). 3개 함수에서 5건의 비효율 발견.
     가장 큰 원인: 캐싱 없는 LLM 호출 (Token 99.9%).
     최적화 시 약 88% SCI 절감이 예상됩니다."
    """
    grade_info = GRADE_INFO.get(sci.grade, GRADE_INFO["F"])

    # 첫 줄: SCI 점수 + 등급
    line1 = (
        f"SCI {sci.sci_score} gCO₂eq/R "
        f"({grade_info['emoji']} {sci.grade}등급 — {grade_info['label']})"
    )

    # 둘째 줄: 발견 사항 요약
    high_findings = [f for f in findings if f.severity == "high"]
    if high_findings:
        top = high_findings[0]
        line2 = (
            f"가장 큰 원인: {top.function_name}() — {top.problem}. "
            f"예상 절감: {top.estimated_reduction}."
        )
    elif findings:
        line2 = f"{len(findings)}건의 개선 가능 항목이 발견되었습니다."
    else:
        line2 = "에너지 비효율 패턴이 발견되지 않았습니다."

    # 셋째 줄: 함수/줄 수 통계
    line3 = (
        f"분석: {analysis.total_functions}개 함수, "
        f"{analysis.total_lines}줄, "
        f"DB 호출 {analysis.total_db_calls}건, "
        f"LLM 호출 {analysis.total_llm_calls}건."
    )

    return f"{line1}\n{line2}\n{line3}"
