"""
energy-aware 스케줄러 — 신규 에이전트 (+1, C2 M2)
=================================================
탄소 강도(gCO2/kWh)와 전기 단가(USD/kWh) 신호를 받아 배치 실행
**리전**을 결정하는 앞단(front-stage) 의사결정자.

설계 원칙:
- 기존 5-에이전트(parser→analyzer→scorer→optimizer→verifier) 파이프라인
  계약은 **건드리지 않는다**. 스케줄러는 그 앞에서 "어디서/지금 할지"만 정한다.
- 신호 소스는 sci.carbon_intensity / sci.electricity_price 의 순수 함수를
  그대로 재사용한다 (region 추상화 SSOT 공유).
- 도메인 정책(탄소 ceiling)은 여기서 verdict(ok|warn|block)로 환원하고,
  거버넌스 집행·감사는 el_supervisor 게이트(PDP)가 담당한다. 즉 이 모듈은
  "판정"만 하고 "거부"는 supervisor가 한다 (PEP/PDP 분리).

면접 포인트:
"같은 코드라도 어느 리전에서 도는지에 따라 탄소·비용이 수 배 차이납니다.
 스케줄러는 가용 리전 중 가장 낮은 탄소·가격을 고르고, 전부 임계를 넘으면
 지금 돌리지 말고 미루라고 권고합니다 — energy-aware 배치 결정입니다."
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from sci.carbon_intensity import get_carbon_intensity
from sci.electricity_price import get_electricity_price


# ================================================================
# 기본 정책값 (회장님 확정: block >= 500, warn >= 350 gCO2/kWh)
# ================================================================
DEFAULT_BLOCK_CEILING = 500.0   # gCO2/kWh 이상이면 dispatch 거부(delay 권고)
DEFAULT_WARN_CEILING = 350.0    # gCO2/kWh 이상이면 허용하되 경고
DEFAULT_CARBON_WEIGHT = 0.7     # 탄소 vs 전기료 가중치 (0~1, 나머지는 가격)


# ================================================================
# 데이터 구조
# ================================================================
@dataclass(frozen=True)
class RegionSignal:
    """후보 리전 하나의 신호 + 정규화 점수 (낮을수록 우수)."""
    region: str
    carbon_intensity: float   # gCO2/kWh
    electricity_price: float  # USD/kWh
    score: float              # 가중 정규화 점수 (0~1, 낮을수록 좋음)


@dataclass(frozen=True)
class SchedulingDecision:
    """스케줄러 결정 — /schedule 응답과 게이트 입력의 원천."""
    selected_region: str
    selected_carbon_intensity: float
    selected_electricity_price: float
    recommendation: str       # "dispatch" | "delay"
    verdict: str              # "ok" | "warn" | "block"
    rationale: str
    ranked: list[RegionSignal] = field(default_factory=list)


# ================================================================
# 스케줄러 본체
# ================================================================
def _normalize(values: Sequence[float]) -> list[float]:
    """min-max 정규화 → [0,1]. 전부 동일하면 모두 0 (분모 0 회피)."""
    lo, hi = min(values), max(values)
    span = hi - lo
    if span == 0:
        return [0.0 for _ in values]
    return [(v - lo) / span for v in values]


def schedule(
    candidate_regions: Sequence[str],
    *,
    carbon_block_ceiling: float = DEFAULT_BLOCK_CEILING,
    carbon_warn_ceiling: float = DEFAULT_WARN_CEILING,
    carbon_weight: float = DEFAULT_CARBON_WEIGHT,
) -> SchedulingDecision:
    """가용 리전 중 최저 탄소·가격 리전을 선택하고 verdict를 판정한다.

    Args:
        candidate_regions: 후보 리전 코드 목록 (예: ["FR", "PL"]). 비면 ValueError.
        carbon_block_ceiling: 선택 리전 탄소가 이 값 이상이면 verdict=block(거부 대상).
        carbon_warn_ceiling: 이 값 이상이면 verdict=warn(허용+경고).
        carbon_weight: 탄소 가중치(0~1). 가격 가중치는 (1 - carbon_weight).

    Returns:
        SchedulingDecision. 선택 리전의 탄소가
          - >= block_ceiling → verdict="block", recommendation="delay"
          - >= warn_ceiling  → verdict="warn",  recommendation="dispatch"
          - 그 외            → verdict="ok",    recommendation="dispatch"
    """
    if not candidate_regions:
        raise ValueError("candidate_regions must not be empty")
    if not 0.0 <= carbon_weight <= 1.0:
        raise ValueError("carbon_weight must be in [0, 1]")

    regions = list(dict.fromkeys(candidate_regions))  # 중복 제거, 순서 보존
    carbons = [get_carbon_intensity(r) for r in regions]
    prices = [get_electricity_price(r) for r in regions]

    norm_carbon = _normalize(carbons)
    norm_price = _normalize(prices)
    price_weight = 1.0 - carbon_weight

    signals = [
        RegionSignal(
            region=r,
            carbon_intensity=c,
            electricity_price=p,
            score=round(carbon_weight * nc + price_weight * np_, 6),
        )
        for r, c, p, nc, np_ in zip(regions, carbons, prices, norm_carbon, norm_price)
    ]
    # 점수 오름차순(최우수 먼저), 동점이면 탄소 낮은 쪽 우선
    ranked = sorted(signals, key=lambda s: (s.score, s.carbon_intensity))
    best = ranked[0]

    if best.carbon_intensity >= carbon_block_ceiling:
        verdict, recommendation = "block", "delay"
        rationale = (
            f"All candidate regions exceed the carbon block ceiling "
            f"({carbon_block_ceiling:.0f} gCO2/kWh): best is {best.region} at "
            f"{best.carbon_intensity:.0f}. Recommend delaying dispatch until a "
            f"greener window or region is available."
        )
    elif best.carbon_intensity >= carbon_warn_ceiling:
        verdict, recommendation = "warn", "dispatch"
        rationale = (
            f"Selected {best.region} ({best.carbon_intensity:.0f} gCO2/kWh, "
            f"{best.electricity_price:.3f} USD/kWh): above the warn ceiling "
            f"({carbon_warn_ceiling:.0f}) but below block. Dispatch allowed with a warning."
        )
    else:
        verdict, recommendation = "ok", "dispatch"
        rationale = (
            f"Selected {best.region} ({best.carbon_intensity:.0f} gCO2/kWh, "
            f"{best.electricity_price:.3f} USD/kWh): lowest weighted carbon/price "
            f"among {len(regions)} candidate(s), within policy."
        )

    return SchedulingDecision(
        selected_region=best.region,
        selected_carbon_intensity=best.carbon_intensity,
        selected_electricity_price=best.electricity_price,
        recommendation=recommendation,
        verdict=verdict,
        rationale=rationale,
        ranked=ranked,
    )
