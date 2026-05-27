"""
지역별 전기 단가 데이터
========================
P (Electricity Price) = 전력 1kWh당 비용 (USD/kWh)

지역마다 전력 시장 구조·세제·발전 믹스가 달라 같은 코드라도
실행 지역에 따라 운영 비용이 달라진다.

데이터 출처 (2023~2024 평균, residential 기준):
- IEA World Energy Prices 2023
- Ember Electricity Data Explorer 2024
- US EIA Form 826 (2024 average retail price)
- KEPCO 공시 주택용 단가 (2023)
- Eurostat NRG_PC_204 (EU household, 2023 H2)
- AER · Genesis · SP Group 공시 (오세아니아/싱가포르)

비용 산출에서의 역할: Cost = E x P
                              ~~~ 이 값

실시간 단가 API 연동(예: KEPCO open API · EIA API · ENTSO-E)은
향후 확장 범위. 현재는 위 통계 기본값 사용.

설계 노트:
    carbon_intensity.py와 동일한 region 추상화를 공유한다.
    클라우드 리전 → 국가 매핑은 carbon_intensity.CLOUD_REGION_MAPPING을
    SSOT로 재사용한다 (두 모듈이 매핑 테이블을 따로 들면 drift가 생긴다).
"""
from typing import Optional

from .carbon_intensity import CLOUD_REGION_MAPPING


# ================================================================
# 지역별 전기 단가 (USD/kWh) — 2023~2024 평균
# ================================================================
ELECTRICITY_PRICE_BY_REGION = {
    # --- 아시아 ---
    "KR": 0.095,    # 한국 — KEPCO 주택용 평균 (~125 KRW/kWh 환산)
    "JP": 0.180,    # 일본 — 도쿄전력 가정용 평균
    "CN": 0.085,    # 중국 — 거주용 평균
    "IN": 0.080,    # 인도 — Tier-1 도시 가정용
    "SG": 0.220,    # 싱가포르 — SP Group 가정용

    # --- 북미 ---
    "US": 0.160,    # 미국 (전국 평균) — EIA 2024 residential
    "US-CA": 0.270, # 캘리포니아 — PG&E 평균
    "US-TX": 0.130, # 텍사스 — ERCOT 가정용
    "CA": 0.100,    # 캐나다 — 수력 우세, 전국 평균

    # --- 유럽 ---
    "DE": 0.400,    # 독일 — Eurostat 2023 H2 household
    "FR": 0.250,    # 프랑스 — EDF Tarif Bleu
    "GB": 0.340,    # 영국 — Ofgem price cap 2024
    "SE": 0.200,    # 스웨덴 — Nordic spot 평균
    "NO": 0.100,    # 노르웨이 — 수력 풍부
    "PL": 0.220,    # 폴란드 — Eurostat 2023 H2

    # --- 오세아니아 ---
    "AU": 0.280,    # 호주 — AER 가정용 평균
    "NZ": 0.180,    # 뉴질랜드 — Genesis Energy 평균
}


# ================================================================
# 통화 정보
# ================================================================
# 현재 모든 단가는 USD 기준으로 통일.
# 향후 통화 변환(KRW/EUR/JPY 표기) 확장 시 cost.py에서 분기.
DEFAULT_CURRENCY = "USD"


def get_electricity_price(
    region: str = "KR",
    cloud_region: Optional[str] = None,
) -> float:
    """
    지역별 전기 단가 조회 (USD/kWh)

    사용 우선순위:
    1. cloud_region이 주어지면 → 클라우드 리전 매핑으로 국가 코드 변환
    2. region만 주어지면 → 국가 코드로 직접 조회
    3. 모두 없으면 → 한국 기본값 (0.095 USD/kWh)

    Args:
        region: 국가/지역 코드 (ISO 3166-1 alpha-2 또는 US-CA 형태)
        cloud_region: AWS/GCP/Azure 리전 코드 (선택)

    Returns:
        전기 단가 (USD/kWh)

    Note:
        carbon_intensity.get_carbon_intensity()와 동일한 폴백 정책.
        미지원 region/cloud_region은 모두 "KR" 단가로 폴백.
    """
    if cloud_region:
        region = CLOUD_REGION_MAPPING.get(cloud_region, "KR")

    return ELECTRICITY_PRICE_BY_REGION.get(
        region, ELECTRICITY_PRICE_BY_REGION["KR"]
    )


def get_all_regions() -> dict:
    """전체 지역별 전기 단가 데이터 반환 (원본 보호용 copy)"""
    return ELECTRICITY_PRICE_BY_REGION.copy()
