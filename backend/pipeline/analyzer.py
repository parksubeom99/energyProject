"""
3축 에너지 분석기 — 파이프라인 ② 단계
========================================
ParseResult(파서 출력) → EnergyBreakdown + SCI 점수

역할:
- parser.py의 출력(함수 목록, DB/API/LLM 호출)을 받아
- 3축 에너지 추정(Compute/Data/Token)을 수행하고
- SCI 공식 엔진(sci/)을 호출하여 최종 점수를 산출

흐름:
  코드 → parser.parse_code() → ParseResult
       → analyzer.analyze() → AnalysisResult (SCI 점수 + 3축 상세 + 함수별 근거)
"""
from dataclasses import dataclass, field

from pipeline.parser import ParseResult, FunctionInfo
from sci.formula import calculate_sci, SCIResult
from sci.energy_model import (
    estimate_compute_energy,
    estimate_data_energy,
    estimate_token_energy,
    EnergyBreakdown,
)


# ================================================================
# 함수별 실행 횟수 추정 기본값
# ================================================================
# 정적 분석이므로 실제 실행 횟수는 알 수 없다.
# 루프 내부 호출 등을 고려한 보수적 추정치 사용.
DEFAULT_EXECUTIONS_PER_FUNCTION = 10

# LLM 호출당 평균 추정 토큰 수 (입력+출력)
DEFAULT_TOKENS_PER_LLM_CALL = 2000

# 함수당 평균 실행 시간 추정 (초)
BASE_EXECUTION_TIME = 0.001  # 1ms 기본


@dataclass
class FunctionAnalysis:
    """함수 단위 분석 결과 — 근거 생성(scorer)에 사용"""
    name: str
    lineno: int
    end_lineno: int
    cyclomatic_complexity: int
    nested_loop_depth: int
    compute_energy_kwh: float
    data_energy_kwh: float
    token_energy_kwh: float
    total_energy_kwh: float
    issues: list = field(default_factory=list)  # 발견된 비효율 패턴


@dataclass
class AnalysisResult:
    """전체 분석 결과 — scorer.py의 입력"""
    # SCI 점수
    sci_result: SCIResult

    # 3축 에너지 브레이크다운
    energy_breakdown: EnergyBreakdown

    # 함수별 상세 분석
    function_analyses: list  # FunctionAnalysis 리스트

    # 요약 통계
    total_functions: int
    total_lines: int
    total_db_calls: int
    total_api_calls: int
    total_llm_calls: int
    total_loops: int
    max_nested_depth: int

    # 발견된 이슈 (전체)
    issues: list = field(default_factory=list)


def analyze(
    parse_result: ParseResult,
    carbon_intensity: float = 450.0,
    embodied_carbon: float = 10.0,
    functional_unit: int = 1000,
    cpu_profile: str = "cloud_default",
) -> AnalysisResult:
    """
    파싱 결과를 받아 3축 에너지 분석 + SCI 점수 산출

    파이프라인: ParseResult → 함수별 에너지 추정 → 합산 → SCI 공식

    Args:
        parse_result: parser.parse_code()의 출력
        carbon_intensity: I — 탄소 강도 (기본값 한국 450)
        embodied_carbon: M — 내재 탄소 (기본값 10 gCO2)
        functional_unit: R — 기능 단위 (기본값 1000)
        cpu_profile: CPU TDP 프로필

    Returns:
        AnalysisResult — SCI 점수 + 3축 상세 + 함수별 근거
    """
    # === 함수별 에너지 분석 ===
    function_analyses = []
    total_compute = 0.0
    total_data = 0.0
    total_token = 0.0
    all_issues = []

    for func in parse_result.functions:
        func_analysis = _analyze_function(func, cpu_profile)
        function_analyses.append(func_analysis)

        total_compute += func_analysis.compute_energy_kwh
        total_data += func_analysis.data_energy_kwh
        total_token += func_analysis.token_energy_kwh
        all_issues.extend(func_analysis.issues)

    # === 전역 스코프 호출 에너지 추가 ===
    global_data_energy = _estimate_global_data_energy(parse_result)
    global_token_energy = _estimate_global_token_energy(parse_result)
    total_data += global_data_energy
    total_token += global_token_energy

    # === 3축 에너지 합산 ===
    total_energy = total_compute + total_data + total_token
    energy_breakdown = EnergyBreakdown(
        compute_energy_kwh=round(total_compute, 10),
        data_energy_kwh=round(total_data, 10),
        token_energy_kwh=round(total_token, 10),
        total_energy_kwh=round(total_energy, 10),
        compute_details={"function_count": len(parse_result.functions)},
        data_details={
            "total_db_calls": _count_total_db_calls(parse_result),
            "total_api_calls": _count_total_api_calls(parse_result),
        },
        token_details={
            "total_llm_calls": _count_total_llm_calls(parse_result),
        },
    )

    # === SCI 공식 적용 ===
    sci_result = calculate_sci(
        energy_kwh=total_energy,
        carbon_intensity=carbon_intensity,
        embodied_carbon=embodied_carbon,
        functional_unit=functional_unit,
    )

    # === 요약 통계 ===
    total_loops = sum(f.loop_count for f in parse_result.functions)
    max_depth = max(
        (f.nested_loop_depth for f in parse_result.functions), default=0
    )

    return AnalysisResult(
        sci_result=sci_result,
        energy_breakdown=energy_breakdown,
        function_analyses=function_analyses,
        total_functions=len(parse_result.functions),
        total_lines=parse_result.total_lines,
        total_db_calls=_count_total_db_calls(parse_result),
        total_api_calls=_count_total_api_calls(parse_result),
        total_llm_calls=_count_total_llm_calls(parse_result),
        total_loops=total_loops,
        max_nested_depth=max_depth,
        issues=all_issues,
    )


# ================================================================
# 함수 단위 에너지 분석
# ================================================================
def _analyze_function(
    func: FunctionInfo,
    cpu_profile: str,
) -> FunctionAnalysis:
    """
    단일 함수의 3축 에너지 추정 + 비효율 패턴 탐지

    비효율 패턴:
    1. [Compute] 중첩 루프 depth >= 2 → O(n²) 이상
    2. [Data]    DB 호출 3건+ → N+1 쿼리 의심
    3. [Token]   LLM 호출이 루프 안에 있을 가능성 → 캐싱 필요
    """
    issues = []

    # --- Compute Energy ---
    # 중첩 루프가 깊으면 실행 시간이 기하급수적 증가
    execution_time = BASE_EXECUTION_TIME
    if func.nested_loop_depth >= 2:
        # O(n²) 이상: 실행 시간 = base × 10^(depth-1)
        execution_time *= 10 ** (func.nested_loop_depth - 1)
        issues.append({
            "type": "compute",
            "severity": "high" if func.nested_loop_depth >= 3 else "medium",
            "line": func.lineno,
            "message": f"O(n^{func.nested_loop_depth}) 중첩 루프 — "
                       f"depth {func.nested_loop_depth}",
            "suggestion": "dict/set 조회로 O(n) 변환 검토",
        })

    compute_energy, _ = estimate_compute_energy(
        cyclomatic_complexity=func.cyclomatic_complexity,
        estimated_executions=DEFAULT_EXECUTIONS_PER_FUNCTION,
        cpu_profile=cpu_profile,
        execution_time_seconds=execution_time,
    )

    # --- Data Energy ---
    db_call_count = len(func.db_calls)
    # execute만 카운트 (fetchall 등은 결과 수신이므로 에너지 낮음)
    simple_queries = sum(
        1 for c in func.db_calls if c["method"] == "execute"
    )
    # 2건 이상이면 N+1 의심 (1회 JOIN으로 대체 가능한 개별 쿼리)
    if simple_queries >= 2:
        issues.append({
            "type": "data",
            "severity": "high" if simple_queries >= 4 else "medium",
            "line": func.db_calls[0]["line"] if func.db_calls else func.lineno,
            "message": f"N+1 쿼리 의심 — {simple_queries}건 개별 SELECT",
            "suggestion": "JOIN 기반 1회 쿼리로 변환 검토",
        })

    api_call_count = len(func.api_calls)
    data_energy, _ = estimate_data_energy(
        simple_queries=simple_queries,
        complex_queries=max(0, db_call_count - simple_queries),
        network_requests=api_call_count,
    )

    # --- Token Energy ---
    llm_call_count = len(func.llm_calls)
    estimated_tokens = llm_call_count * DEFAULT_TOKENS_PER_LLM_CALL

    if llm_call_count > 0 and func.loop_count > 0:
        # 루프 안에서 LLM 호출 → 캐싱 없으면 토큰 낭비
        estimated_tokens *= DEFAULT_EXECUTIONS_PER_FUNCTION
        issues.append({
            "type": "token",
            "severity": "high",
            "line": func.llm_calls[0]["line"] if func.llm_calls else func.lineno,
            "message": f"루프 내 LLM 호출 — 캐싱 없이 {llm_call_count}건 반복 호출",
            "suggestion": "lru_cache 또는 Redis 캐싱으로 중복 호출 제거",
        })

    token_energy, _ = estimate_token_energy(
        total_tokens=estimated_tokens,
        api_calls=llm_call_count,
    )

    total = compute_energy + data_energy + token_energy

    return FunctionAnalysis(
        name=func.name,
        lineno=func.lineno,
        end_lineno=func.end_lineno,
        cyclomatic_complexity=func.cyclomatic_complexity,
        nested_loop_depth=func.nested_loop_depth,
        compute_energy_kwh=round(compute_energy, 10),
        data_energy_kwh=round(data_energy, 10),
        token_energy_kwh=round(token_energy, 10),
        total_energy_kwh=round(total, 10),
        issues=issues,
    )


# ================================================================
# 전역 스코프 에너지 추정
# ================================================================
def _estimate_global_data_energy(pr: ParseResult) -> float:
    """전역 스코프 DB/API 호출 에너지"""
    energy, _ = estimate_data_energy(
        simple_queries=len(pr.global_db_calls),
        network_requests=len(pr.global_api_calls),
    )
    return energy


def _estimate_global_token_energy(pr: ParseResult) -> float:
    """전역 스코프 LLM 호출 에너지"""
    tokens = len(pr.global_llm_calls) * DEFAULT_TOKENS_PER_LLM_CALL
    energy, _ = estimate_token_energy(total_tokens=tokens)
    return energy


# ================================================================
# 집계 유틸
# ================================================================
def _count_total_db_calls(pr: ParseResult) -> int:
    """전체 DB 호출 수 (함수 내 + 전역)"""
    func_calls = sum(len(f.db_calls) for f in pr.functions)
    return func_calls + len(pr.global_db_calls)


def _count_total_api_calls(pr: ParseResult) -> int:
    """전체 API 호출 수 (함수 내 + 전역)"""
    func_calls = sum(len(f.api_calls) for f in pr.functions)
    return func_calls + len(pr.global_api_calls)


def _count_total_llm_calls(pr: ParseResult) -> int:
    """전체 LLM 호출 수 (함수 내 + 전역)"""
    func_calls = sum(len(f.llm_calls) for f in pr.functions)
    return func_calls + len(pr.global_llm_calls)
