"""
인증/인가 Pydantic 모델
========================
User, Role, Token 관련 요청/응답 스키마.

RBAC 구조:
- free: 일 5회 분석 (기본)
- pro: 일 1000회 분석
- admin: 무제한 + 관리 기능
"""
from enum import Enum
from datetime import datetime

from pydantic import BaseModel, Field


# ================================================================
# 역할(Role) 열거형
# ================================================================
class Role(str, Enum):
    """사용자 역할 — RBAC 기반 접근 제어"""
    FREE = "free"      # 무료 티어: 일 5회 분석
    PRO = "pro"        # 프로 티어: 일 1000회 분석
    ADMIN = "admin"    # 관리자: 무제한 + 관리 기능


# ================================================================
# 사용자 모델
# ================================================================
class UserBase(BaseModel):
    """사용자 기본 스키마"""
    username: str = Field(..., min_length=3, max_length=50)
    role: Role = Role.FREE


class UserCreate(UserBase):
    """회원가입 요청"""
    password: str = Field(..., min_length=8)


class UserInDB(UserBase):
    """DB 저장용 (해시 비밀번호 포함)"""
    hashed_password: str
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    daily_usage: int = 0           # 오늘 사용 횟수
    last_usage_date: str = ""      # 마지막 사용 날짜 (YYYY-MM-DD)


class UserResponse(UserBase):
    """사용자 정보 응답 (비밀번호 제외)"""
    is_active: bool
    daily_usage: int = 0


# ================================================================
# 토큰 모델
# ================================================================
class TokenRequest(BaseModel):
    """로그인 요청"""
    username: str
    password: str


class TokenResponse(BaseModel):
    """
    JWT 토큰 응답

    access_token: 30분 유효. API 호출 시 Authorization 헤더에 사용.
    refresh_token: 7일 유효. access_token 만료 시 갱신용.
    token_type: "bearer" (OAuth2 표준)
    """
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access Token 만료까지 초")
    role: Role


class RefreshRequest(BaseModel):
    """토큰 갱신 요청"""
    refresh_token: str


class TokenPayload(BaseModel):
    """JWT 페이로드 (디코딩 결과)"""
    sub: str               # subject = username
    role: Role             # 사용자 역할
    type: str = "access"   # "access" | "refresh"
    exp: int = 0           # 만료 시간 (Unix timestamp)
    jti: str = ""          # JWT ID (RTR에서 사용)


# ================================================================
# 분석 요청/응답 모델
# ================================================================
class AnalyzeRequest(BaseModel):
    """코드 분석 요청 (JSON 방식)"""
    source_code: str = Field(..., min_length=1, description="분석할 Python 코드")
    region: str = Field(default="KR", description="지역 코드 (탄소 강도)")
    functional_unit: int = Field(default=1, ge=1, description="기능 단위 (R)")


class AnalyzeResponse(BaseModel):
    """코드 분석 응답 — ScoreReport의 API 표현"""
    analysis_id: str
    sci_score: float
    grade: str
    grade_label: str
    grade_color: str
    summary_text: str
    axis_summaries: list
    findings: list
    total_functions: int
    total_lines: int
    total_energy_kwh: float
    total_carbon_gco2: float
    # === 비용 노출 (덩어리 2) ===
    estimated_cost: float       # 1회당 비용 (E x P)
    cost_per_kwh: float          # 적용된 지역 전기 단가 (USD/kWh)
    cost_currency: str           # 통화 코드 (현재 "USD" 고정)
    analyzed_at: str


class HistoryItem(BaseModel):
    """분석 이력 항목"""
    analysis_id: str
    sci_score: float
    grade: str
    total_lines: int
    analyzed_at: str
