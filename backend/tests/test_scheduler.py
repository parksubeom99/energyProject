"""
energy-aware 스케줄러 단위 테스트 (C2)
======================================
순수 함수 검증 — 서버/ECS 없이 schedule() 만 본다.

기준값 (sci/carbon_intensity, sci/electricity_price):
  FR 60 gCO2/kWh / 0.250 USD   KR 450 / 0.095   PL 650 / 0.220
  US 380 / 0.160               IN 700 / 0.080
정책: block >= 500, warn >= 350.
"""
import pytest

from pipeline.scheduler import schedule, SchedulingDecision


def test_selects_lowest_carbon_region():
    """저탄소 리전(FR)을 고른다 — 가격이 더 비싸도 탄소 가중이 높으므로."""
    d = schedule(["FR", "PL"])
    assert d.selected_region == "FR"
    assert d.verdict == "ok"
    assert d.recommendation == "dispatch"
    # ranked 최우수가 선택 리전과 일치
    assert d.ranked[0].region == "FR"


def test_selects_best_among_three():
    """혼합 후보에서도 최저 탄소(FR)를 선택."""
    d = schedule(["US", "FR", "PL"])
    assert d.selected_region == "FR"
    assert d.verdict == "ok"


def test_warn_band_region():
    """KR(450)은 warn 밴드(350~500) — 허용하되 경고."""
    d = schedule(["KR"])
    assert d.selected_region == "KR"
    assert d.verdict == "warn"
    assert d.recommendation == "dispatch"


def test_block_when_best_exceeds_ceiling():
    """후보가 전부 임계 초과(PL 650)면 block + delay 권고."""
    d = schedule(["PL"])
    assert d.verdict == "block"
    assert d.recommendation == "delay"
    assert "delay" in d.rationale.lower()


def test_block_multi_all_bad():
    """여러 후보가 모두 임계 초과(PL 650, IN 700) → 최선도 block."""
    d = schedule(["PL", "IN"])
    assert d.verdict == "block"
    # 둘 중 더 나은(낮은 탄소) PL이 선택되지만 그래도 block
    assert d.selected_region == "PL"


def test_empty_candidates_raises():
    with pytest.raises(ValueError):
        schedule([])


def test_invalid_weight_raises():
    with pytest.raises(ValueError):
        schedule(["FR"], carbon_weight=1.5)


def test_dedup_preserves_order():
    """중복 후보는 제거되고 점수 산출은 정상."""
    d = schedule(["FR", "FR", "PL"])
    regions = [s.region for s in d.ranked]
    assert regions.count("FR") == 1
    assert set(regions) == {"FR", "PL"}


def test_ceiling_is_tunable():
    """임계를 낮추면 평소 ok이던 리전도 block이 될 수 있다."""
    # FR(60)은 기본 ok지만 block_ceiling=50으로 낮추면 block
    d = schedule(["FR"], carbon_block_ceiling=50.0, carbon_warn_ceiling=10.0)
    assert d.verdict == "block"


def test_price_weight_can_flip_choice():
    """탄소 가중을 0으로 두면 최저가 리전이 선택된다 (IN 0.080)."""
    # 후보: FR(0.250) vs IN(0.080). carbon_weight=0 → 가격만 → IN
    d = schedule(["FR", "IN"], carbon_weight=0.0)
    assert d.selected_region == "IN"


def test_returns_decision_type():
    d = schedule(["FR"])
    assert isinstance(d, SchedulingDecision)
    assert d.selected_carbon_intensity == 60
