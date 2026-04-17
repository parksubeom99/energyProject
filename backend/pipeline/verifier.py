"""
Before/After SCI 비교 검증 — 파이프라인 ⑤ 단계
=================================================
Optimizer가 산출한 최적화 코드를 다시 분석 파이프라인에 넣어
실제로 SCI 점수가 감소했는지 검증한다.

흐름:
  original_code → Parser → Analyzer → Scorer → Before SCI
  optimized_code → Parser → Analyzer → Scorer → After SCI
  → Before vs After 비교 → VerificationResult

면접 포인트:
"Claude가 만든 코드를 그대로 신뢰하지 않습니다.
 최적화 코드를 다시 동일한 파이프라인으로 분석하여
 실제로 SCI가 감소했는지 수치로 검증합니다.
 Before 460(F) → After 55(D) = 88% 감소를 실증합니다."
"""
from dataclasses import dataclass, field

from pipeline.parser import parse_code
from pipeline.analyzer import analyze
from pipeline.scorer import score, ScoreReport
from pipeline.optimizer import OptimizationResult


@dataclass
class VerificationResult:
    """
    Before/After SCI 검증 결과 — 대시보드 CodeDiff 컴포넌트 입력

    이 객체가 GreenPulse 분석의 최종 산출물이다:
    "코드를 넣으면 수치와 근거가 나오고, 최적화 코드를 산출하고,
     실제로 개선됐는지 수치로 증명한다."
    """
    # Before (원본)
    before_sci: float
    before_grade: str
    before_report: ScoreReport

    # After (최적화)
    after_sci: float
    after_grade: str
    after_report: ScoreReport

    # 비교
    sci_reduction: float         # SCI 감소량 (before - after)
    sci_reduction_pct: float     # SCI 감소율 (%)
    is_improved: bool            # After < Before 여부

    # 최적화 정보
    optimization: OptimizationResult
    applied_fixes: list = field(default_factory=list)

    # 검증 상태
    status: str = "verified"     # "verified" | "no_improvement" | "failed"


def verify(
    optimization: OptimizationResult,
    carbon_intensity: float = 450.0,
    embodied_carbon: float = 10.0,
    functional_unit: int = 1,
) -> VerificationResult:
    """
    Before/After SCI 검증 실행

    최적화 결과를 받아 원본과 최적화 코드 모두를
    동일한 파이프라인(Parser → Analyzer → Scorer)으로 분석하고
    SCI 점수 변화를 검증한다.

    Args:
        optimization: optimizer.optimize()의 출력
        carbon_intensity: 탄소 강도 (동일 조건 비교 위해 통일)
        embodied_carbon: 내재 탄소 (동일 조건)
        functional_unit: 기능 단위 (동일 조건)

    Returns:
        VerificationResult — Before/After 비교 + 감소율
    """
    # 최적화 코드가 유효하지 않으면 검증 불가
    if not optimization.is_valid or not optimization.optimized_code:
        before_report = _analyze_code(
            optimization.original_code,
            carbon_intensity, embodied_carbon, functional_unit,
        )
        return VerificationResult(
            before_sci=before_report.sci_score,
            before_grade=before_report.grade,
            before_report=before_report,
            after_sci=before_report.sci_score,
            after_grade=before_report.grade,
            after_report=before_report,
            sci_reduction=0,
            sci_reduction_pct=0,
            is_improved=False,
            optimization=optimization,
            status="failed",
        )

    # === Before 분석 ===
    before_report = _analyze_code(
        optimization.original_code,
        carbon_intensity, embodied_carbon, functional_unit,
    )

    # === After 분석 ===
    after_report = _analyze_code(
        optimization.optimized_code,
        carbon_intensity, embodied_carbon, functional_unit,
    )

    # === Before vs After 비교 ===
    reduction = before_report.sci_score - after_report.sci_score
    reduction_pct = (
        (reduction / before_report.sci_score * 100)
        if before_report.sci_score > 0
        else 0
    )
    is_improved = after_report.sci_score < before_report.sci_score

    status = "verified" if is_improved else "no_improvement"

    return VerificationResult(
        before_sci=before_report.sci_score,
        before_grade=before_report.grade,
        before_report=before_report,
        after_sci=after_report.sci_score,
        after_grade=after_report.grade,
        after_report=after_report,
        sci_reduction=round(reduction, 4),
        sci_reduction_pct=round(reduction_pct, 1),
        is_improved=is_improved,
        optimization=optimization,
        applied_fixes=optimization.applied_fixes,
        status=status,
    )


def _analyze_code(
    code: str,
    carbon_intensity: float,
    embodied_carbon: float,
    functional_unit: int,
) -> ScoreReport:
    """코드 → 분석 파이프라인 실행 → ScoreReport"""
    parsed = parse_code(code)
    analysis = analyze(
        parsed,
        carbon_intensity=carbon_intensity,
        embodied_carbon=embodied_carbon,
        functional_unit=functional_unit,
    )
    return score(analysis)
