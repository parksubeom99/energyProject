"""
지역별 탄소 강도 데이터
========================
I (Carbon Intensity) = 전력 1kWh 생산 시 배출되는 CO2 (gCO2/kWh)

지역마다 발전 믹스(석탄, 원자력, 재생에너지 등)가 다르므로
같은 코드라도 실행 지역에 따라 탄소 배출량이 달라진다.

데이터 출처:
- IEA (International Energy Agency) 2023 통계 (기본값)
- Electricity Maps API (프로덕션 실시간 연동 예정)

SCI 공식에서의 역할: SCI = ((E x I) + M) / R
                              ~~~ 이 값
"""
from typing import Optional


# ================================================================
# IEA 2023 기준 국가별 탄소 강도 (gCO2/kWh)
# ================================================================
CARBON_INTENSITY_BY_REGION = {
    # --- 아시아 ---
    "KR": 450,     # 한국 — 석탄+LNG 비중 높음
    "JP": 470,     # 일본 — 화석연료 의존
    "CN": 580,     # 중국 — 석탄 비중 높음
    "IN": 700,     # 인도 — 석탄 의존 최고
    "SG": 410,     # 싱가포르 — LNG 중심

    # --- 북미 ---
    "US": 380,     # 미국 (전국 평균)
    "US-CA": 210,  # 캘리포니아 — 재생에너지 선도
    "US-TX": 400,  # 텍사스 — 화석연료 + 풍력 혼합
    "CA": 120,     # 캐나다 — 수력 발전 비중 높음

    # --- 유럽 ---
    "DE": 350,     # 독일 — 석탄 감축 중
    "FR": 60,      # 프랑스 — 원자력 75%+
    "GB": 230,     # 영국 — 해상풍력 확대
    "SE": 30,      # 스웨덴 — 수력+원자력
    "NO": 20,      # 노르웨이 — 수력 90%+
    "PL": 650,     # 폴란드 — 석탄 의존

    # --- 오세아니아 ---
    "AU": 550,     # 호주 — 석탄+태양광
    "NZ": 100,     # 뉴질랜드 — 지열+수력
}


# ================================================================
# 클라우드 리전 -> 국가 코드 매핑
# ================================================================
# AWS/GCP/Azure 리전을 국가 코드로 변환하여 탄소 강도 조회
CLOUD_REGION_MAPPING = {
    # --- AWS ---
    "ap-northeast-2": "KR",      # 서울
    "ap-northeast-1": "JP",      # 도쿄
    "ap-northeast-3": "JP",      # 오사카
    "ap-southeast-1": "SG",      # 싱가포르
    "us-east-1": "US",           # 버지니아
    "us-east-2": "US",           # 오하이오
    "us-west-1": "US-CA",        # 캘리포니아
    "us-west-2": "US-CA",        # 오레곤
    "eu-west-1": "GB",           # 아일랜드 (근사)
    "eu-central-1": "DE",        # 프랑크푸르트
    "eu-north-1": "SE",          # 스톡홀름
    "ca-central-1": "CA",        # 몬트리올

    # --- GCP ---
    "asia-northeast3": "KR",     # 서울
    "asia-northeast1": "JP",     # 도쿄
    "us-central1": "US",         # 아이오와
    "europe-west1": "FR",        # 벨기에 (근사)
    "europe-north1": "SE",       # 핀란드 (근사)

    # --- Azure ---
    "koreacentral": "KR",        # 한국 중부
    "japaneast": "JP",           # 일본 동부
    "eastus": "US",              # 미국 동부
    "westeurope": "DE",          # 서유럽
    "northeurope": "GB",         # 북유럽
}


def get_carbon_intensity(
    region: str = "KR",
    cloud_region: Optional[str] = None,
) -> float:
    """
    지역별 탄소 강도 조회 (gCO2/kWh)

    사용 우선순위:
    1. cloud_region이 주어지면 → 클라우드 리전 매핑으로 국가 코드 변환
    2. region만 주어지면 → 국가 코드로 직접 조회
    3. 모두 없으면 → 한국 기본값 (450)

    Args:
        region: 국가/지역 코드 (ISO 3166-1 alpha-2)
        cloud_region: AWS/GCP/Azure 리전 코드 (선택)

    Returns:
        탄소 강도 (gCO2/kWh)

    Note:
        프로덕션에서는 Electricity Maps API로 실시간 조회 예정.
        현재는 IEA 2023 통계 기본값 사용.
    """
    # 클라우드 리전 → 국가 코드 변환
    if cloud_region:
        region = CLOUD_REGION_MAPPING.get(cloud_region, "KR")

    # 국가 코드 → 탄소 강도 조회 (없으면 한국 기본값)
    return CARBON_INTENSITY_BY_REGION.get(region, 450)


def get_all_regions() -> dict:
    """전체 지역별 탄소 강도 데이터 반환"""
    return CARBON_INTENSITY_BY_REGION.copy()


def get_cloud_regions() -> dict:
    """클라우드 리전 매핑 데이터 반환"""
    return CLOUD_REGION_MAPPING.copy()
