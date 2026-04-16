"""
GreenPulse 환경 설정 모듈
=========================
ISO/IEC 21031:2024 SCI(Software Carbon Intensity) 기반
코드 에너지 분석 + AI 자동 최적화 플랫폼

SOURCE = "SCI_ISO21031" — 이 프로젝트의 Single Source of Truth
모든 점수 산출은 이 표준의 공식을 따른다.
"""
import os
from dataclasses import dataclass, field


# ================================================================
# Single Source of Truth — 프로젝트 정체성
# ================================================================
SOURCE = "SCI_ISO21031"  # ISO/IEC 21031:2024 기반 SCI 점수 체계


@dataclass
class Settings:
    """
    애플리케이션 환경 설정

    환경 변수로 오버라이드 가능하며, 기본값은 로컬 개발 환경 기준.
    프로덕션에서는 K8s ConfigMap/Secret으로 주입.
    """

    # --- 앱 기본 정보 ---
    APP_NAME: str = "GreenPulse"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = field(
        default_factory=lambda: os.getenv("DEBUG", "false").lower() == "true"
    )

    # --- API 서버 (L3 FastAPI) ---
    API_HOST: str = field(default_factory=lambda: os.getenv("API_HOST", "0.0.0.0"))
    API_PORT: int = field(default_factory=lambda: int(os.getenv("API_PORT", "8000")))

    # --- JWT 인증 (L4 보안) ---
    JWT_SECRET: str = field(
        default_factory=lambda: os.getenv(
            "JWT_SECRET", "greenpulse-dev-secret-change-in-prod"
        )
    )
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_EXPIRE_MINUTES: int = 30    # Access Token 유효기간: 30분
    JWT_REFRESH_EXPIRE_DAYS: int = 7       # Refresh Token 유효기간: 7일

    # --- 데이터베이스 (L6 PostgreSQL) ---
    DATABASE_URL: str = field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL",
            "postgresql://greenpulse:greenpulse@postgres:5432/greenpulse",
        )
    )

    # --- 캐시 (L6 Redis) ---
    REDIS_URL: str = field(
        default_factory=lambda: os.getenv("REDIS_URL", "redis://redis:6379/0")
    )

    # --- 메시징 (L7 Kafka) ---
    KAFKA_BOOTSTRAP_SERVERS: str = field(
        default_factory=lambda: os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
    )
    KAFKA_TOPIC_ANALYSIS: str = "greenpulse.analysis.request"   # 분석 요청 토픽
    KAFKA_TOPIC_RESULT: str = "greenpulse.analysis.result"      # 분석 결과 토픽
    KAFKA_GROUP_ID: str = "greenpulse-worker"

    # --- SCI 기본값 (ISO/IEC 21031:2024) ---
    # SCI = ((E x I) + M) / R
    DEFAULT_CARBON_INTENSITY: float = 450.0   # I: 한국 전력 탄소 강도 (gCO2/kWh)
    DEFAULT_EMBODIED_CARBON: float = 10.0     # M: 기본 내재 탄소 (gCO2)
    DEFAULT_FUNCTIONAL_UNIT: int = 1000       # R: 기본 기능 단위 (API 호출 1000건)

    # --- Claude API (L4 최적화 코드 생성) ---
    CLAUDE_API_KEY: str = field(
        default_factory=lambda: os.getenv("CLAUDE_API_KEY", "")
    )
    CLAUDE_MODEL: str = "claude-sonnet-4-20250514"

    # --- SCI 등급 기준 (gCO2eq/R) ---
    GRADE_A_MAX: float = 10.0    # A: 0 ~ 10   (매우 효율적)
    GRADE_B_MAX: float = 25.0    # B: 10 ~ 25  (양호)
    GRADE_C_MAX: float = 50.0    # C: 25 ~ 50  (보통)
    GRADE_D_MAX: float = 100.0   # D: 50 ~ 100 (개선 필요)
    # F: 100+ (심각한 비효율)

    # --- Rate Limiting ---
    RATE_LIMIT_FREE: int = 5     # 무료 티어: 일 5회 분석
    RATE_LIMIT_PRO: int = 1000   # 프로 티어: 일 1000회 분석


# 전역 설정 인스턴스 — 앱 전체에서 import하여 사용
settings = Settings()
