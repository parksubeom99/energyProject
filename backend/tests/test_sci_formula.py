"""
SCI 공식 엔진 단위 테스트
==========================
ISO/IEC 21031:2024 | SCI = ((E x I) + M) / R

ROADMAP 검증 조건:
1. E=1.0, I=450, M=10, R=1000 -> SCI = 0.46 확인
2. E=0 -> SCI = M/R 확인
3. R=0 -> ValueError (ZeroDivisionError 방지) 확인
"""
import sys
import os

import pytest

# 프로젝트 루트(backend/)를 Python 경로에 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sci.formula import calculate_sci, _calculate_grade
from sci.energy_model import (
    estimate_compute_energy,
    estimate_data_energy,
    estimate_token_energy,
    estimate_total_energy,
)
from sci.carbon_intensity import get_carbon_intensity, get_all_regions
from sci.embodied_carbon import estimate_embodied_carbon


# ================================================================
# SCI 공식 테스트 — ISO/IEC 21031:2024
# ================================================================
class TestSCIFormula:
    """SCI = ((E x I) + M) / R 공식 검증"""

    def test_basic_calculation(self):
        """ROADMAP 검증 #1: E=1.0, I=450, M=10, R=1000 -> SCI = 0.46"""
        result = calculate_sci(
            energy_kwh=1.0,
            carbon_intensity=450,
            embodied_carbon=10,
            functional_unit=1000,
        )
        # SCI = ((1.0 x 450) + 10) / 1000 = 460 / 1000 = 0.46
        assert result.sci_score == 0.46
        assert result.operational_carbon == 450.0
        assert result.total_carbon == 460.0

    def test_zero_energy(self):
        """ROADMAP 검증 #2: E=0 -> SCI = M/R"""
        result = calculate_sci(
            energy_kwh=0,
            carbon_intensity=450,
            embodied_carbon=10,
            functional_unit=1000,
        )
        # SCI = ((0 x 450) + 10) / 1000 = 0.01
        assert result.sci_score == 0.01
        assert result.operational_carbon == 0.0

    def test_zero_functional_unit(self):
        """ROADMAP 검증 #3: R=0 -> ValueError"""
        with pytest.raises(ValueError, match="기능 단위"):
            calculate_sci(
                energy_kwh=1.0,
                carbon_intensity=450,
                embodied_carbon=10,
                functional_unit=0,
            )

    def test_negative_energy_raises_error(self):
        """음수 에너지 -> ValueError"""
        with pytest.raises(ValueError, match="에너지"):
            calculate_sci(energy_kwh=-1.0)

    def test_negative_carbon_intensity_raises_error(self):
        """음수 탄소 강도 -> ValueError"""
        with pytest.raises(ValueError, match="탄소 강도"):
            calculate_sci(energy_kwh=1.0, carbon_intensity=-100)

    def test_negative_embodied_raises_error(self):
        """음수 내재 탄소 -> ValueError"""
        with pytest.raises(ValueError, match="내재 탄소"):
            calculate_sci(energy_kwh=1.0, embodied_carbon=-5)

    def test_high_energy_grade_f(self):
        """높은 에너지 -> F등급"""
        result = calculate_sci(
            energy_kwh=10.0,
            carbon_intensity=450,
            embodied_carbon=100,
            functional_unit=10,
        )
        # SCI = ((10 x 450) + 100) / 10 = 4600 / 10 = 460
        assert result.sci_score == 460.0
        assert result.grade == "F"

    def test_low_energy_grade_a(self):
        """낮은 에너지 -> A등급"""
        result = calculate_sci(
            energy_kwh=0.001,
            carbon_intensity=450,
            embodied_carbon=1,
            functional_unit=1000,
        )
        # SCI = ((0.001 x 450) + 1) / 1000 = 1.45 / 1000 = 0.00145
        assert result.grade == "A"

    def test_default_values(self):
        """기본값 사용 시 정상 동작"""
        result = calculate_sci(energy_kwh=0.5)
        assert result.carbon_intensity == 450.0  # 한국 기본값
        assert result.functional_unit == 1000
        assert result.sci_score > 0


# ================================================================
# 등급 산출 테스트
# ================================================================
class TestGradeCalculation:
    """SCI 등급 경계값 테스트 (A ~ F)"""

    def test_grade_a_boundary(self):
        """A등급: 0 ~ 10"""
        assert _calculate_grade(0) == "A"
        assert _calculate_grade(5.0) == "A"
        assert _calculate_grade(10.0) == "A"

    def test_grade_b_boundary(self):
        """B등급: 10 ~ 25"""
        assert _calculate_grade(10.01) == "B"
        assert _calculate_grade(25.0) == "B"

    def test_grade_c_boundary(self):
        """C등급: 25 ~ 50"""
        assert _calculate_grade(25.01) == "C"
        assert _calculate_grade(50.0) == "C"

    def test_grade_d_boundary(self):
        """D등급: 50 ~ 100"""
        assert _calculate_grade(50.01) == "D"
        assert _calculate_grade(100.0) == "D"

    def test_grade_f_boundary(self):
        """F등급: 100+"""
        assert _calculate_grade(100.01) == "F"
        assert _calculate_grade(999.99) == "F"


# ================================================================
# 에너지 추정 모델 테스트 — 3축 분석
# ================================================================
class TestEnergyModel:
    """Compute / Data / Token 에너지 추정 검증"""

    def test_compute_energy_basic(self):
        """Compute Energy 기본 추정"""
        energy, details = estimate_compute_energy(
            cyclomatic_complexity=10,
            estimated_executions=100,
        )
        assert energy > 0
        assert details["complexity_factor"] == 0.6  # CC 6~10 -> 0.6

    def test_compute_energy_complexity_scaling(self):
        """높은 복잡도 -> 높은 에너지"""
        low_energy, _ = estimate_compute_energy(cyclomatic_complexity=3)
        high_energy, _ = estimate_compute_energy(cyclomatic_complexity=25)
        assert high_energy > low_energy

    def test_compute_energy_execution_scaling(self):
        """실행 횟수에 비례 (부동소수점 round 오차 허용)"""
        single, _ = estimate_compute_energy(estimated_executions=1)
        hundred, _ = estimate_compute_energy(estimated_executions=100)
        assert abs(hundred - single * 100) < 1e-8

    def test_data_energy_n_plus_1_vs_join(self):
        """N+1 쿼리(100건) > JOIN(1건) — 핵심 비교"""
        n1_energy, _ = estimate_data_energy(simple_queries=100)
        join_energy, _ = estimate_data_energy(complex_queries=1)
        assert n1_energy > join_energy

    def test_data_energy_zero_io(self):
        """IO 없음 -> 에너지 0"""
        energy, details = estimate_data_energy()
        assert energy == 0
        assert details["total_io_operations"] == 0

    def test_token_energy_claude_sonnet(self):
        """Token Energy: 10,000 토큰 x Claude Sonnet"""
        energy, details = estimate_token_energy(
            total_tokens=10000,
            model="claude-sonnet",
        )
        # 10000 / 1000 x 0.0005 = 10 x 0.0005 = 0.005
        assert energy == 0.005
        assert details["energy_per_1k_tokens"] == 0.0005

    def test_token_energy_zero_tokens(self):
        """토큰 0 -> 에너지 0"""
        energy, _ = estimate_token_energy(total_tokens=0)
        assert energy == 0

    def test_total_energy_combines_all(self):
        """3축 에너지 합산 검증"""
        result = estimate_total_energy(
            compute_args={"cyclomatic_complexity": 10},
            data_args={"simple_queries": 50},
            token_args={"total_tokens": 5000},
        )
        assert result.total_energy_kwh > 0
        # 합산 검증: total = compute + data + token
        expected_total = (
            result.compute_energy_kwh
            + result.data_energy_kwh
            + result.token_energy_kwh
        )
        assert abs(result.total_energy_kwh - round(expected_total, 10)) < 1e-10


# ================================================================
# 탄소 강도 테스트
# ================================================================
class TestCarbonIntensity:
    """지역별 탄소 강도 (I) 테스트"""

    def test_korea_default(self):
        """한국 기본값: 450 gCO2/kWh"""
        assert get_carbon_intensity("KR") == 450

    def test_france_nuclear(self):
        """프랑스 (원자력 75%+): 60 gCO2/kWh"""
        assert get_carbon_intensity("FR") == 60

    def test_norway_hydro(self):
        """노르웨이 (수력 90%+): 20 gCO2/kWh"""
        assert get_carbon_intensity("NO") == 20

    def test_unknown_region_fallback(self):
        """알 수 없는 지역 -> 한국 기본값 450"""
        assert get_carbon_intensity("XX") == 450

    def test_cloud_region_aws_seoul(self):
        """AWS ap-northeast-2 -> 한국 -> 450"""
        intensity = get_carbon_intensity(cloud_region="ap-northeast-2")
        assert intensity == 450

    def test_cloud_region_aws_stockholm(self):
        """AWS eu-north-1 -> 스웨덴 -> 30"""
        intensity = get_carbon_intensity(cloud_region="eu-north-1")
        assert intensity == 30

    def test_all_regions_coverage(self):
        """전체 지역 데이터 10개 이상 존재"""
        regions = get_all_regions()
        assert len(regions) > 10


# ================================================================
# 내재 탄소 테스트
# ================================================================
class TestEmbodiedCarbon:
    """하드웨어 내재 탄소 (M) 추정 테스트"""

    def test_default_instance(self):
        """기본 인스턴스 1시간 사용 -> 양수"""
        carbon, details = estimate_embodied_carbon(usage_hours=1.0)
        assert carbon > 0
        assert details["instance_type"] == "default"

    def test_usage_hours_proportional(self):
        """사용 시간에 비례"""
        carbon_1h, _ = estimate_embodied_carbon(usage_hours=1.0)
        carbon_2h, _ = estimate_embodied_carbon(usage_hours=2.0)
        assert abs(carbon_2h - carbon_1h * 2) < 0.01

    def test_larger_instance_more_carbon(self):
        """큰 인스턴스 -> 더 많은 내재 탄소"""
        micro, _ = estimate_embodied_carbon(instance_type="t3.micro")
        xlarge, _ = estimate_embodied_carbon(instance_type="m5.xlarge")
        assert xlarge > micro

    def test_custom_values(self):
        """사용자 지정값 적용"""
        carbon, _ = estimate_embodied_carbon(
            custom_total_gco2=100_000,
            custom_lifespan_years=5,
            usage_hours=1.0,
        )
        # 100,000 / (5 x 8,760) x 1.0 = 100,000 / 43,800 = 2.2831
        expected = 100_000 / (5 * 8760) * 1.0
        assert abs(carbon - round(expected, 4)) < 0.01
