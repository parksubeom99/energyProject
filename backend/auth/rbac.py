"""
역할 기반 접근 제어 (RBAC) + Rate Limiting
============================================
Role별 API 사용량 제한:
- free: 일 5회 분석
- pro: 일 1000회 분석
- admin: 무제한

면접 포인트:
"RBAC으로 무료/프로 유저를 분리하고, Rate Limiting으로 API 남용을 방지합니다.
 무료 유저가 일 5회를 초과하면 429 Too Many Requests를 반환하고,
 프로 업그레이드를 유도합니다."

프로덕션: Redis INCR + EXPIRE로 분산 환경에서도 정확한 카운팅.
개발: 인메모리 dict로 구현.
"""
from datetime import date
from dataclasses import dataclass, field

from auth.models import Role
from config import settings


# ================================================================
# 사용량 추적 (프로덕션: Redis)
# ================================================================
@dataclass
class UsageRecord:
    """일일 사용량 레코드"""
    count: int = 0
    date: str = ""  # YYYY-MM-DD


# 인메모리 사용량 저장소 (프로덕션: Redis Hash)
_usage_store: dict[str, UsageRecord] = {}


# ================================================================
# Role별 제한 설정
# ================================================================
ROLE_LIMITS = {
    Role.FREE: settings.RATE_LIMIT_FREE,      # 일 5회
    Role.PRO: settings.RATE_LIMIT_PRO,         # 일 1000회
    Role.ADMIN: -1,                             # 무제한 (-1)
}


def check_rate_limit(username: str, role: Role) -> tuple[bool, dict]:
    """
    Rate Limit 확인

    Args:
        username: 사용자명
        role: 사용자 역할

    Returns:
        (허용 여부, 상세 정보)
        상세 정보: {
            "allowed": True/False,
            "limit": 일 제한 횟수,
            "used": 오늘 사용 횟수,
            "remaining": 남은 횟수,
            "reset_at": 다음 리셋 시간 (자정),
        }
    """
    limit = ROLE_LIMITS.get(role, ROLE_LIMITS[Role.FREE])

    # admin은 무제한
    if limit == -1:
        return True, {
            "allowed": True,
            "limit": -1,
            "used": 0,
            "remaining": -1,
            "reset_at": "unlimited",
        }

    today = date.today().isoformat()

    # 사용량 레코드 조회 (없으면 새로 생성)
    record = _usage_store.get(username, UsageRecord())

    # 날짜가 바뀌면 리셋
    if record.date != today:
        record = UsageRecord(count=0, date=today)

    remaining = max(0, limit - record.count)
    allowed = record.count < limit

    info = {
        "allowed": allowed,
        "limit": limit,
        "used": record.count,
        "remaining": remaining,
        "reset_at": f"{today}T23:59:59",
    }

    return allowed, info


def increment_usage(username: str) -> None:
    """사용 횟수 증가 (분석 성공 시 호출)"""
    today = date.today().isoformat()
    record = _usage_store.get(username, UsageRecord())

    # 날짜 리셋
    if record.date != today:
        record = UsageRecord(count=0, date=today)

    record.count += 1
    _usage_store[username] = record


def get_usage(username: str) -> dict:
    """현재 사용량 조회"""
    today = date.today().isoformat()
    record = _usage_store.get(username, UsageRecord())

    if record.date != today:
        return {"used": 0, "date": today}

    return {"used": record.count, "date": record.date}


def reset_usage(username: str) -> None:
    """사용량 초기화 (테스트용)"""
    if username in _usage_store:
        del _usage_store[username]


def clear_all_usage() -> None:
    """전체 사용량 초기화 (테스트용)"""
    _usage_store.clear()
