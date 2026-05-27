"""
electricity_price.py 단위 테스트
=================================
검증 대상:
    - 지역별 단가 조회 (KR/US/DE 등)
    - 클라우드 리전 매핑 (carbon_intensity와 SSOT 공유)
    - 미지원 지역/리전 폴백 (KR 단가)
    - 데이터 무결성 (양수, 합리적 범위, get_all_regions copy)
"""
import sys
import os

import pytest

# 프로젝트 루트(backend/)를 Python 경로에 추가 — 기존 테스트 패턴 동일
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sci.electricity_price import (
    DEFAULT_CURRENCY,
    ELECTRICITY_PRICE_BY_REGION,
    get_all_regions,
    get_electricity_price,
)


# ================================================================
# 1. 기본 단가 조회
# ================================================================
class TestGetElectricityPrice:
    def test_kr_explicit(self):
        assert get_electricity_price("KR") == 0.095

    def test_kr_is_function_default(self):
        # 인자 생략 시 KR
        assert get_electricity_price() == 0.095

    def test_us_price(self):
        assert get_electricity_price("US") == 0.160

    def test_de_high_price(self):
        # 독일이 한국보다 4배 이상 비싸야 (절감 시나리오 핵심 가정)
        assert get_electricity_price("DE") > get_electricity_price("KR") * 4

    def test_us_ca_higher_than_us(self):
        # 캘리포니아는 미국 평균보다 비싸야
        assert get_electricity_price("US-CA") > get_electricity_price("US")

    def test_no_lowest_in_europe(self):
        # 노르웨이가 수력으로 유럽 최저 부근
        assert get_electricity_price("NO") < get_electricity_price("DE")


# ================================================================
# 2. 미지원 지역 폴백
# ================================================================
class TestUnknownRegionFallback:
    def test_unknown_region_returns_kr_price(self):
        assert get_electricity_price("XX") == get_electricity_price("KR")

    def test_unknown_region_explicit_value(self):
        assert get_electricity_price("ZZ") == 0.095

    def test_empty_string_falls_back(self):
        assert get_electricity_price("") == 0.095


# ================================================================
# 3. 클라우드 리전 매핑
# ================================================================
class TestCloudRegionMapping:
    def test_aws_seoul_maps_to_kr(self):
        assert get_electricity_price(cloud_region="ap-northeast-2") == get_electricity_price("KR")

    def test_aws_us_west_1_maps_to_us_ca(self):
        assert get_electricity_price(cloud_region="us-west-1") == get_electricity_price("US-CA")

    def test_gcp_tokyo_maps_to_jp(self):
        assert get_electricity_price(cloud_region="asia-northeast1") == get_electricity_price("JP")

    def test_azure_eastus_maps_to_us(self):
        assert get_electricity_price(cloud_region="eastus") == get_electricity_price("US")

    def test_unknown_cloud_region_fallback_to_kr(self):
        assert get_electricity_price(cloud_region="mars-central-1") == get_electricity_price("KR")

    def test_cloud_region_overrides_region(self):
        # cloud_region이 우선 — region 인자 무시
        result = get_electricity_price(region="US", cloud_region="ap-northeast-2")
        assert result == get_electricity_price("KR")


# ================================================================
# 4. 데이터 무결성
# ================================================================
class TestDataIntegrity:
    def test_all_regions_positive_price(self):
        for region, price in ELECTRICITY_PRICE_BY_REGION.items():
            assert price > 0, f"{region} price must be positive: {price}"

    def test_kr_present_for_fallback(self):
        # 폴백 기본값으로 사용되므로 반드시 존재
        assert "KR" in ELECTRICITY_PRICE_BY_REGION

    def test_get_all_regions_returns_copy(self):
        regions = get_all_regions()
        regions["KR"] = 999.0
        # 원본 변경 안 됨
        assert ELECTRICITY_PRICE_BY_REGION["KR"] == 0.095

    def test_default_currency_is_usd(self):
        assert DEFAULT_CURRENCY == "USD"

    def test_realistic_price_range(self):
        # USD/kWh 합리적 범위 (0.01 ~ 1.00)
        for region, price in ELECTRICITY_PRICE_BY_REGION.items():
            assert 0.01 <= price <= 1.00, f"{region} out of range: {price}"
