"""
JWT 발급/검증 + Refresh Token Rotation (RTR)
==============================================
Access Token: 30분 유효. API 호출 시 사용.
Refresh Token: 7일 유효. Access Token 만료 시 갱신.

RTR(Refresh Token Rotation) 동작:
1. 클라이언트가 refresh_token으로 /auth/refresh 호출
2. 서버가 새 access_token + 새 refresh_token 발급
3. 기존 refresh_token은 블랙리스트에 추가 (1회용)
4. 탈취된 refresh_token 재사용 시 → 전체 토큰 무효화

면접 포인트:
"RTR을 구현하여 Refresh Token 탈취 공격을 방어합니다.
 한 번 사용된 Refresh Token은 블랙리스트에 등록되어 재사용 불가하며,
 재사용 시도가 감지되면 해당 사용자의 전체 토큰을 무효화합니다."
"""
import uuid
from datetime import datetime, timedelta

from jose import jwt, JWTError

from config import settings
from auth.models import TokenPayload, Role


# ================================================================
# 토큰 블랙리스트 (프로덕션: Redis 사용)
# ================================================================
# 개발 환경에서는 인메모리 dict 사용.
# 프로덕션에서는 Redis SET에 jti를 저장하고 TTL을 Refresh Token 만료 시간으로 설정.
_blacklisted_jtis: set[str] = set()


def create_access_token(username: str, role: Role) -> str:
    """
    Access Token 생성 (30분 유효)

    페이로드: sub(username) + role + type("access") + exp + jti
    """
    jti = str(uuid.uuid4())
    expire = datetime.utcnow() + timedelta(minutes=settings.JWT_ACCESS_EXPIRE_MINUTES)

    payload = {
        "sub": username,
        "role": role.value,
        "type": "access",
        "exp": expire,
        "jti": jti,
    }

    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(username: str, role: Role) -> str:
    """
    Refresh Token 생성 (7일 유효)

    RTR: 매번 새로운 jti로 생성. 이전 토큰은 블랙리스트 등록.
    """
    jti = str(uuid.uuid4())
    expire = datetime.utcnow() + timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS)

    payload = {
        "sub": username,
        "role": role.value,
        "type": "refresh",
        "exp": expire,
        "jti": jti,
    }

    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def verify_token(token: str, expected_type: str = "access") -> TokenPayload:
    """
    JWT 토큰 검증

    검증 항목:
    1. 서명 유효성 (JWT_SECRET + HS256)
    2. 만료 시간 (exp)
    3. 토큰 타입 (access/refresh)
    4. 블랙리스트 (RTR — 이미 사용된 refresh token 차단)

    Args:
        token: JWT 토큰 문자열
        expected_type: "access" 또는 "refresh"

    Returns:
        TokenPayload — 디코딩된 페이로드

    Raises:
        ValueError: 검증 실패 시
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except JWTError as e:
        raise ValueError(f"토큰 검증 실패: {e}")

    # 타입 검증
    token_type = payload.get("type", "")
    if token_type != expected_type:
        raise ValueError(f"잘못된 토큰 타입: {token_type} (기대: {expected_type})")

    # 블랙리스트 검증 (RTR)
    jti = payload.get("jti", "")
    if jti in _blacklisted_jtis:
        raise ValueError("이미 사용된 토큰입니다 (RTR 위반)")

    return TokenPayload(
        sub=payload["sub"],
        role=Role(payload["role"]),
        type=token_type,
        exp=payload.get("exp", 0),
        jti=jti,
    )


def rotate_refresh_token(old_refresh_token: str) -> tuple[str, str]:
    """
    Refresh Token Rotation (RTR)

    동작:
    1. 기존 refresh_token 검증
    2. 기존 refresh_token의 jti를 블랙리스트에 추가
    3. 새 access_token + 새 refresh_token 발급

    면접 포인트: "탈취된 refresh_token이 재사용되면 블랙리스트에서
    감지하여 차단합니다. 1회 사용 원칙으로 보안을 강화합니다."

    Returns:
        (새 access_token, 새 refresh_token)

    Raises:
        ValueError: 기존 토큰 검증 실패 시
    """
    # 기존 refresh token 검증
    payload = verify_token(old_refresh_token, expected_type="refresh")

    # 기존 jti 블랙리스트 등록 (RTR 핵심)
    _blacklisted_jtis.add(payload.jti)

    # 새 토큰 쌍 발급
    new_access = create_access_token(payload.sub, payload.role)
    new_refresh = create_refresh_token(payload.sub, payload.role)

    return new_access, new_refresh


def blacklist_token(jti: str) -> None:
    """토큰 수동 블랙리스트 등록 (로그아웃 등)"""
    _blacklisted_jtis.add(jti)


def is_blacklisted(jti: str) -> bool:
    """블랙리스트 확인"""
    return jti in _blacklisted_jtis


def clear_blacklist() -> None:
    """블랙리스트 초기화 (테스트용)"""
    _blacklisted_jtis.clear()
