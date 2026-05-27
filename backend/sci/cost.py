"""
전력 비용 산출 엔진
====================
Cost = E x P

E = 에너지 소비량 (kWh) — energy_model.estimate_total_energy()로 추정
P = 전기 단가 (USD/kWh) — electricity_price.get_electricity_price()

단위: USD per functional unit (1회 실행 / 1 API 호출 / 1 트랜잭션)

이 모듈은 SCI 공식(formula.calculate_sci)과 대칭 구조다.
    - 탄소: SCI  = ((E x I) + M) / R  ← formula.py (ISO/IEC 21031:2024)
    - 비용: Cost =   E x P            ← 이 모듈
둘 다 E(에너지)를 공통 입력으로 받지만 변환 계수가 다르다.

ISO 21031:2024 범위 밖. SCI 공식은 절대 수정하지 않는다.
"""
from dataclasses import dataclass
from typing import Optional

from .carbon_intensity import CLOUD_REGION_MAPPING
from .electricity_price import DEFAULT_CURRENCY, get_electricity_price


@dataclass
class CostResult:
    """전력 비용 산출 결과 — 대시보드의 비용 게이지·절감 카드에 표시"""

    estimated_cost: float        # 1회당 비용 (E x P)
    cost_per_kwh: float          # 적용된 단가 (USD/kWh)
    energy_kwh: float            # 입력 에너지 (kWh)
    region: str                  # 단가 조회에 사용된 지역 코드 (cloud 매핑 후)
    currency: str                # 통화 (현재 USD 고정)

    # === 옵션: 월/년 환산 (monthly_executions가 주어졌을 때만 채움) ===
    monthly_executions: Optional[int] = None
    monthly_cost: Optional[float] = None
    yearly_cost: Optional[float] = None

    # === 옵션: Before/After 절감 (baseline_energy_kwh가 주어졌을 때만) ===
    baseline_energy_kwh: Optional[float] = None
    baseline_cost: Optional[float] = None
    savings: Optional[float] = None
    savings_percent: Optional[float] = None
    monthly_savings: Optional[float] = None
    yearly_savings: Optional[float] = None


def estimate_cost(
    energy_kwh: float,
    region: str = "KR",
    cloud_region: Optional[str] = None,
    monthly_executions: Optional[int] = None,
    baseline_energy_kwh: Optional[float] = None,
) -> CostResult:
    """
    전력 비용 산출 — Cost = E x P

    Args:
        energy_kwh: E — 에너지 소비량 (kWh). 음수 불가.
        region: 단가 조회 지역. cloud_region이 있으면 무시.
        cloud_region: 클라우드 리전 (AWS/GCP/Azure). 우선 적용.
        monthly_executions: 월간 실행 횟수. 주어지면 월/년 비용 환산.
        baseline_energy_kwh: 개선 전(베이스라인) 에너지. 주어지면 절감액 계산.

    Returns:
        CostResult — 1회당 비용 + 선택적으로 월/년 환산·절감액

    Raises:
        ValueError: energy_kwh, monthly_executions, baseline_energy_kwh 음수일 때
    """
    # === 입력 유효성 검증 ===
    if energy_kwh < 0:
        raise ValueError(f"에너지(E)는 0 이상이어야 합니다: {energy_kwh}")
    if monthly_executions is not None and monthly_executions < 0:
        raise ValueError(
            f"월간 실행 횟수는 0 이상이어야 합니다: {monthly_executions}"
        )
    if baseline_energy_kwh is not None and baseline_energy_kwh < 0:
        raise ValueError(
            f"베이스라인 에너지는 0 이상이어야 합니다: {baseline_energy_kwh}"
        )

    # === 지역 해석 (cloud_region 우선) ===
    if cloud_region:
        resolved_region = CLOUD_REGION_MAPPING.get(cloud_region, "KR")
    else:
        resolved_region = region

    # === 단가 조회 & 1회당 비용 ===
    price = get_electricity_price(region=resolved_region)
    estimated = energy_kwh * price

    result = CostResult(
        estimated_cost=round(estimated, 10),
        cost_per_kwh=price,
        energy_kwh=energy_kwh,
        region=resolved_region,
        currency=DEFAULT_CURRENCY,
    )

    # === 옵션: 월/년 환산 ===
    if monthly_executions is not None:
        monthly = estimated * monthly_executions
        result.monthly_executions = monthly_executions
        result.monthly_cost = round(monthly, 10)
        result.yearly_cost = round(monthly * 12, 10)

    # === 옵션: Before/After 절감 ===
    if baseline_energy_kwh is not None:
        baseline_cost = baseline_energy_kwh * price
        savings = baseline_cost - estimated
        savings_percent = (
            (savings / baseline_cost * 100.0) if baseline_cost > 0 else 0.0
        )
        result.baseline_energy_kwh = baseline_energy_kwh
        result.baseline_cost = round(baseline_cost, 10)
        result.savings = round(savings, 10)
        result.savings_percent = round(savings_percent, 4)

        # 절감액의 월/년 환산은 monthly_executions와 함께 있을 때만 의미
        if monthly_executions is not None:
            result.monthly_savings = round(savings * monthly_executions, 10)
            result.yearly_savings = round(savings * monthly_executions * 12, 10)

    return result
