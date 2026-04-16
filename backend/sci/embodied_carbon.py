"""
하드웨어 내재 탄소 추정
========================
M (Embodied Carbon) = 하드웨어 제조 시 배출된 탄소를 사용 기간으로 할당

공식: M = (total_embodied_gCO2 / expected_lifespan_hours) x usage_hours
단위: gCO2

SCI 공식에서의 역할: SCI = ((E x I) + M) / R
                                     ~~~ 이 값

참조:
- Dell/Lenovo/HP 제품 탄소 발자국(Product Carbon Footprint) 보고서
- Cloud Carbon Footprint 프로젝트 데이터
- ACM "Chasing Carbon" 논문 (2021)
"""
from typing import Optional


# ================================================================
# 클라우드 인스턴스별 내재 탄소 (gCO2, 제조 시 총 배출량)
# ================================================================
# 참조: Cloud Carbon Footprint 프로젝트 + 제조사 LCA 보고서
INSTANCE_EMBODIED_CARBON = {
    # --- AWS EC2 (추정값) ---
    "t3.micro": {"total_gco2": 100_000, "lifespan_years": 4},
    "t3.small": {"total_gco2": 120_000, "lifespan_years": 4},
    "t3.medium": {"total_gco2": 150_000, "lifespan_years": 4},
    "t3.large": {"total_gco2": 200_000, "lifespan_years": 4},
    "m5.large": {"total_gco2": 300_000, "lifespan_years": 4},
    "m5.xlarge": {"total_gco2": 450_000, "lifespan_years": 4},
    "c5.large": {"total_gco2": 280_000, "lifespan_years": 4},
    "c5.xlarge": {"total_gco2": 420_000, "lifespan_years": 4},
    "r5.large": {"total_gco2": 350_000, "lifespan_years": 4},

    # --- 온프레미스 서버 ---
    "on_premise_small": {"total_gco2": 500_000, "lifespan_years": 5},
    "on_premise_medium": {"total_gco2": 800_000, "lifespan_years": 5},
    "on_premise_large": {"total_gco2": 1_200_000, "lifespan_years": 5},

    # --- 기본값 (클라우드 중소 인스턴스 기준) ---
    "default": {"total_gco2": 200_000, "lifespan_years": 4},
}


def estimate_embodied_carbon(
    instance_type: str = "default",
    usage_hours: float = 1.0,
    custom_total_gco2: Optional[float] = None,
    custom_lifespan_years: Optional[float] = None,
) -> tuple[float, dict]:
    """
    하드웨어 내재 탄소 추정

    공식: M = (total_embodied / lifespan_hours) x usage_hours

    예시:
        t3.medium, 1시간 사용:
        M = (150,000 / (4 x 8760)) x 1 = 150,000 / 35,040 = 4.28 gCO2

    Args:
        instance_type: 클라우드 인스턴스 타입 또는 서버 유형
        usage_hours: 사용 시간 (시간 단위)
        custom_total_gco2: 사용자 지정 총 내재 탄소 (gCO2)
        custom_lifespan_years: 사용자 지정 기대 수명 (년)

    Returns:
        (내재 탄소 gCO2, 상세 내역 dict)
    """
    # 인스턴스 데이터 조회 (없으면 기본값)
    instance_data = INSTANCE_EMBODIED_CARBON.get(
        instance_type, INSTANCE_EMBODIED_CARBON["default"]
    )

    # 사용자 지정값 우선 적용
    total_gco2 = custom_total_gco2 or instance_data["total_gco2"]
    lifespan_years = custom_lifespan_years or instance_data["lifespan_years"]

    # 수명을 시간으로 변환 (1년 = 8,760시간)
    lifespan_hours = lifespan_years * 8760

    # M = (total / lifespan_hours) x usage_hours
    embodied = (total_gco2 / lifespan_hours) * usage_hours

    details = {
        "instance_type": instance_type,
        "total_embodied_gco2": total_gco2,
        "lifespan_years": lifespan_years,
        "lifespan_hours": lifespan_hours,
        "usage_hours": usage_hours,
        "embodied_per_hour": round(total_gco2 / lifespan_hours, 4),
    }

    return round(embodied, 4), details


def get_instance_types() -> dict:
    """사용 가능한 인스턴스 타입 목록 반환 (UI 선택지용)"""
    return {
        k: v for k, v in INSTANCE_EMBODIED_CARBON.items() if k != "default"
    }
