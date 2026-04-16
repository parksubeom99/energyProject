"""
GreenPulse 테스트용 샘플 코드 — "혼합" 패턴
=============================================
효율적인 부분과 비효율적인 부분이 공존하는 현실적 코드.
SCI 점수: 예상 C등급 (25~50 gCO2eq/R)

패턴 혼합:
1. [Compute] O(n) — 효율적 (set 활용)
2. [Data]    N+1 쿼리 — 비효율적 (개선 필요)
3. [Token]   LLM 미호출 — 해당 없음
"""
import sqlite3
from typing import Optional


# ===== [Compute Energy] O(n) — 효율적 =====
# 이 함수는 이미 최적화되어 있음
def find_active_users(users: list[dict]) -> list[dict]:
    """O(n) 필터링 — Compute Energy 효율적"""
    active_ids = set()
    active_users = []
    for user in users:
        if user.get("is_active") and user["id"] not in active_ids:
            active_ids.add(user["id"])
            active_users.append(user)
    return active_users


# ===== [Data Energy] N+1 쿼리 — 비효율적 =====
# 이 함수는 개선이 필요함
def get_user_profiles(user_ids: list) -> list[dict]:
    """N+1 쿼리 — Data Energy 낭비 (개선 대상)"""
    conn = sqlite3.connect("app.db")
    cursor = conn.cursor()

    profiles = []
    for user_id in user_ids:
        # N+1: 유저마다 개별 쿼리
        cursor.execute(
            "SELECT * FROM profiles WHERE user_id = ?", (user_id,)
        )
        profile = cursor.fetchone()
        if profile:
            # 또 N+1: 프로필마다 설정 조회
            cursor.execute(
                "SELECT * FROM settings WHERE user_id = ?", (user_id,)
            )
            settings = cursor.fetchone()
            profiles.append({"profile": profile, "settings": settings})

    conn.close()
    return profiles


# ===== 유틸리티 — 단순 함수 (에너지 중립) =====
def format_report(data: dict) -> str:
    """보고서 포맷팅 — 에너지 영향 미미"""
    lines = [f"=== {data.get('title', 'Report')} ==="]
    for key, value in data.items():
        if key != "title":
            lines.append(f"  {key}: {value}")
    return "\n".join(lines)


# ===== 전체 처리 =====
def process_dashboard():
    """혼합 패턴 — Compute 효율 / Data 비효율"""
    users = [
        {"id": i, "name": f"User_{i}", "is_active": i % 3 != 0}
        for i in range(100)
    ]

    # 1. O(n) 필터링 — OK
    active = find_active_users(users)

    # 2. N+1 쿼리 — 개선 필요
    profiles = get_user_profiles([u["id"] for u in active])

    # 3. 보고서 생성 — 에너지 중립
    report = format_report({
        "title": "Active User Dashboard",
        "total_users": len(users),
        "active_users": len(active),
        "profiles_loaded": len(profiles),
    })
    print(report)
