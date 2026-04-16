"""
SCI 공식 엔진 — ISO/IEC 21031:2024
====================================
SCI = ((E x I) + M) / R

E = 에너지 소비량 (kWh) — 코드가 소비하는 전력
I = 탄소 강도 (gCO2/kWh) — 지역별 전력의 탄소 배출 계수
M = 내재 탄소 (gCO2)     — 하드웨어 제조 시 배출된 탄소의 할당분
R = 기능 단위            — API 호출 1건, 사용자 1명, 트랜잭션 1건 등

단위: gCO2eq / R (기능 단위당 탄소 그램)

참조: https://sci.greensoftware.foundation/
"""
from dataclasses import dataclass


@dataclass
class SCIResult:
    """SCI 점수 산출 결과 — 대시보드에 표시될 데이터"""

    sci_score: float           # 최종 SCI 점수 (gCO2eq/R)
    operational_carbon: float  # 운영 탄소 = E x I (gCO2)
    embodied_carbon: float     # 내재 탄소 = M (gCO2)
    total_carbon: float        # 총 탄소 = (E x I) + M (gCO2)
    energy_kwh: float          # E: 에너지 소비량 (kWh)
    carbon_intensity: float    # I: 탄소 강도 (gCO2/kWh)
    functional_unit: int       # R: 기능 단위
    grade: str                 # 등급 (A ~ F)


def calculate_sci(
    energy_kwh: float,
    carbon_intensity: float = 450.0,
    embodied_carbon: float = 10.0,
    functional_unit: int = 1000,
) -> SCIResult:
    """
    SCI 점수 산출 — ISO/IEC 21031:2024 공식 구현

    이 함수가 GreenPulse의 심장이다.
    모든 분석 결과는 이 공식을 통해 최종 점수로 변환된다.

    Args:
        energy_kwh: E — 에너지 소비량 (kWh). 3축 분석기로 추정.
        carbon_intensity: I — 탄소 강도 (gCO2/kWh). 기본값 한국 450.
        embodied_carbon: M — 내재 탄소 (gCO2). 기본값 10.
        functional_unit: R — 기능 단위. 기본값 1000 API 호출.

    Returns:
        SCIResult — SCI 점수 + 등급 + 상세 내역

    Raises:
        ValueError: R <= 0 (ZeroDivisionError 방지)
        ValueError: E, I, M 이 음수일 때
    """
    # === 입력 유효성 검증 ===
    if functional_unit <= 0:
        raise ValueError(
            f"기능 단위(R)는 양수여야 합니다: {functional_unit}"
        )
    if energy_kwh < 0:
        raise ValueError(
            f"에너지(E)는 0 이상이어야 합니다: {energy_kwh}"
        )
    if carbon_intensity < 0:
        raise ValueError(
            f"탄소 강도(I)는 0 이상이어야 합니다: {carbon_intensity}"
        )
    if embodied_carbon < 0:
        raise ValueError(
            f"내재 탄소(M)는 0 이상이어야 합니다: {embodied_carbon}"
        )

    # === SCI 공식 계산 ===
    # SCI = ((E x I) + M) / R
    operational = energy_kwh * carbon_intensity   # 운영 탄소 (gCO2)
    total = operational + embodied_carbon          # 총 탄소 (gCO2)
    sci_score = total / functional_unit            # SCI 점수 (gCO2eq/R)

    # === 등급 산출 ===
    grade = _calculate_grade(sci_score)

    return SCIResult(
        sci_score=round(sci_score, 4),
        operational_carbon=round(operational, 4),
        embodied_carbon=embodied_carbon,
        total_carbon=round(total, 4),
        energy_kwh=energy_kwh,
        carbon_intensity=carbon_intensity,
        functional_unit=functional_unit,
        grade=grade,
    )


def _calculate_grade(sci_score: float) -> str:
    """
    SCI 점수 -> 등급 변환

    등급 기준 (config.py와 동일):
        A: 0 ~ 10    매우 효율적
        B: 10 ~ 25   양호
        C: 25 ~ 50   보통
        D: 50 ~ 100  개선 필요
        F: 100+      심각한 비효율
    """
    if sci_score <= 10.0:
        return "A"
    elif sci_score <= 25.0:
        return "B"
    elif sci_score <= 50.0:
        return "C"
    elif sci_score <= 100.0:
        return "D"
    else:
        return "F"
