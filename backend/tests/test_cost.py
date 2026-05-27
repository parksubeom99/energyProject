"""
cost.py 단위 테스트
====================
검증 대상:
    - 기본 비용 산출 (Cost = E x P)
    - 클라우드 리전 매핑 (cloud_region 우선)
    - 월/년 환산 (monthly_executions)
    - Before/After 절감액 (baseline_energy_kwh)
    - 입력 검증 (음수 거부)
    - CostResult 구조
"""
import sys
import os

import pytest

# 프로젝트 루트(backend/)를 Python 경로에 추가 — 기존 테스트 패턴 동일
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sci.cost import CostResult, estimate_cost


# ================================================================
# 1. 기본 비용 산출
# ================================================================
class TestEstimateCostBasic:
    def test_basic_kwh_times_price(self):
        # 1 kWh × 0.095 USD/kWh = 0.095 USD
        result = estimate_cost(energy_kwh=1.0, region="KR")
        assert result.estimated_cost == pytest.approx(0.095)
        assert result.cost_per_kwh == 0.095
        assert result.energy_kwh == 1.0
        assert result.region == "KR"
        assert result.currency == "USD"

    def test_zero_energy_zero_cost(self):
        result = estimate_cost(energy_kwh=0.0, region="KR")
        assert result.estimated_cost == 0.0

    def test_de_costs_more_than_kr(self):
        # 같은 kWh — 독일이 한국보다 비쌈 (4배 이상)
        kr = estimate_cost(energy_kwh=10.0, region="KR")
        de = estimate_cost(energy_kwh=10.0, region="DE")
        assert de.estimated_cost > kr.estimated_cost * 4

    def test_unknown_region_fallback_to_kr_price(self):
        result = estimate_cost(energy_kwh=1.0, region="ZZ")
        assert result.cost_per_kwh == 0.095

    def test_default_region_is_kr(self):
        # region 인자 생략
        result = estimate_cost(energy_kwh=1.0)
        assert result.region == "KR"
        assert result.cost_per_kwh == 0.095

    def test_default_currency_usd(self):
        result = estimate_cost(energy_kwh=1.0)
        assert result.currency == "USD"


# ================================================================
# 2. 클라우드 리전 매핑
# ================================================================
class TestCloudRegion:
    def test_cloud_region_resolves_to_country(self):
        result = estimate_cost(energy_kwh=1.0, cloud_region="ap-northeast-2")
        assert result.region == "KR"

    def test_cloud_region_overrides_region(self):
        # region="US"가 무시되고 cloud=서울이 적용
        result = estimate_cost(
            energy_kwh=1.0, region="US", cloud_region="ap-northeast-2"
        )
        assert result.region == "KR"
        assert result.cost_per_kwh == 0.095

    def test_unknown_cloud_region_fallback(self):
        result = estimate_cost(energy_kwh=1.0, cloud_region="mars-1")
        assert result.region == "KR"

    def test_aws_us_west_1_maps_to_us_ca(self):
        result = estimate_cost(energy_kwh=1.0, cloud_region="us-west-1")
        assert result.region == "US-CA"
        assert result.cost_per_kwh == 0.270


# ================================================================
# 3. 월/년 환산
# ================================================================
class TestMonthlyYearly:
    def test_monthly_cost_calculated(self):
        # 1 kWh × 0.16 USD × 10,000 호출 = 1,600 USD/월
        result = estimate_cost(
            energy_kwh=1.0, region="US", monthly_executions=10000
        )
        assert result.monthly_cost == pytest.approx(1600.0)

    def test_yearly_is_12x_monthly(self):
        result = estimate_cost(
            energy_kwh=1.0, region="US", monthly_executions=1000
        )
        assert result.yearly_cost == pytest.approx(result.monthly_cost * 12)

    def test_monthly_optional_none_by_default(self):
        result = estimate_cost(energy_kwh=1.0, region="KR")
        assert result.monthly_cost is None
        assert result.yearly_cost is None
        assert result.monthly_executions is None

    def test_zero_monthly_executions_zero_cost(self):
        result = estimate_cost(
            energy_kwh=1.0, region="KR", monthly_executions=0
        )
        assert result.monthly_cost == 0.0
        assert result.yearly_cost == 0.0
        assert result.monthly_executions == 0

    def test_monthly_executions_preserved(self):
        result = estimate_cost(
            energy_kwh=1.0, region="KR", monthly_executions=5000
        )
        assert result.monthly_executions == 5000


# ================================================================
# 4. Before/After 절감
# ================================================================
class TestSavings:
    def test_savings_when_baseline_higher(self):
        # baseline 10 kWh → 개선 후 4 kWh → 6 kWh 절감 × 0.10 USD = 0.6 USD
        result = estimate_cost(
            energy_kwh=4.0, baseline_energy_kwh=10.0, region="CA"
        )
        assert result.savings == pytest.approx(0.6)
        assert result.baseline_cost == pytest.approx(1.0)

    def test_savings_percent(self):
        # 10 → 4 = 60% 절감
        result = estimate_cost(
            energy_kwh=4.0, baseline_energy_kwh=10.0, region="KR"
        )
        assert result.savings_percent == pytest.approx(60.0)

    def test_no_savings_when_baseline_equal(self):
        result = estimate_cost(
            energy_kwh=5.0, baseline_energy_kwh=5.0, region="KR"
        )
        assert result.savings == 0.0
        assert result.savings_percent == 0.0

    def test_negative_savings_when_regression(self):
        # baseline보다 더 많이 쓴 경우 — 절감 음수
        result = estimate_cost(
            energy_kwh=10.0, baseline_energy_kwh=5.0, region="KR"
        )
        assert result.savings < 0
        assert result.savings_percent < 0

    def test_savings_optional_none_by_default(self):
        result = estimate_cost(energy_kwh=1.0, region="KR")
        assert result.savings is None
        assert result.baseline_cost is None
        assert result.savings_percent is None
        assert result.baseline_energy_kwh is None

    def test_monthly_savings_combined(self):
        # baseline 10 → 4 = 6 kWh 절감 × 0.095 = 0.57 USD/회
        # × 1000 호출 = 570 USD/월, × 12 = 6840 USD/년
        result = estimate_cost(
            energy_kwh=4.0,
            baseline_energy_kwh=10.0,
            region="KR",
            monthly_executions=1000,
        )
        assert result.monthly_savings == pytest.approx(570.0)
        assert result.yearly_savings == pytest.approx(6840.0)

    def test_monthly_savings_none_without_monthly_executions(self):
        # baseline만 있고 monthly_executions가 없으면 월 절감은 None
        result = estimate_cost(
            energy_kwh=4.0, baseline_energy_kwh=10.0, region="KR"
        )
        assert result.monthly_savings is None
        assert result.yearly_savings is None

    def test_savings_percent_when_baseline_zero(self):
        # baseline 0이면 0%로 처리 (ZeroDivisionError 방지)
        result = estimate_cost(
            energy_kwh=0.0, baseline_energy_kwh=0.0, region="KR"
        )
        assert result.savings_percent == 0.0
        assert result.savings == 0.0


# ================================================================
# 5. 입력 검증
# ================================================================
class TestValidation:
    def test_negative_energy_raises(self):
        with pytest.raises(ValueError, match="에너지"):
            estimate_cost(energy_kwh=-1.0, region="KR")

    def test_negative_monthly_executions_raises(self):
        with pytest.raises(ValueError, match="월간"):
            estimate_cost(
                energy_kwh=1.0, region="KR", monthly_executions=-1
            )

    def test_negative_baseline_raises(self):
        with pytest.raises(ValueError, match="베이스라인"):
            estimate_cost(
                energy_kwh=1.0, baseline_energy_kwh=-1.0, region="KR"
            )


# ================================================================
# 6. CostResult 구조
# ================================================================
class TestCostResultStructure:
    def test_result_is_dataclass(self):
        result = estimate_cost(energy_kwh=1.0, region="KR")
        assert isinstance(result, CostResult)

    def test_required_fields_populated(self):
        result = estimate_cost(energy_kwh=1.0, region="KR")
        assert result.estimated_cost is not None
        assert result.cost_per_kwh is not None
        assert result.energy_kwh is not None
        assert result.region is not None
        assert result.currency is not None

    def test_optional_fields_default_none(self):
        # monthly/baseline 인자 없으면 옵션 필드는 모두 None
        result = estimate_cost(energy_kwh=1.0, region="KR")
        assert result.monthly_executions is None
        assert result.monthly_cost is None
        assert result.yearly_cost is None
        assert result.baseline_energy_kwh is None
        assert result.baseline_cost is None
        assert result.savings is None
        assert result.savings_percent is None
        assert result.monthly_savings is None
        assert result.yearly_savings is None
