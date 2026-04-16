"""
GreenPulse 테스트용 샘플 코드 — "좋은" 패턴
=============================================
에너지 효율적인 코드 패턴을 보여주는 샘플입니다.
SCI 점수: 예상 A등급 (0~10 gCO2eq/R)

포함된 효율 패턴:
1. [Compute] O(n) 해시 기반 중복 탐지
2. [Data]    JOIN 기반 1회 쿼리
3. [Token]   LRU 캐싱을 활용한 LLM 호출
"""
import sqlite3
from functools import lru_cache

import requests


# ===== [Compute Energy] O(n) 해시 기반 =====
# set을 사용해 O(n)으로 중복 탐지 — CPU 연산 최소화
def find_duplicates(items: list) -> list:
    """O(n) 해시 기반 — Compute Energy 효율적"""
    seen = set()
    duplicates = set()
    for item in items:
        if item in seen:
            duplicates.add(item)    # set.add = O(1)
        seen.add(item)
    return list(duplicates)


# ===== [Data Energy] JOIN 기반 1회 쿼리 =====
# IN 절 + JOIN으로 한 번에 조회 — DB IO 최소화
def get_user_orders(user_ids: list) -> dict:
    """JOIN 기반 1회 쿼리 — Data Energy 효율적"""
    conn = sqlite3.connect("shop.db")
    cursor = conn.cursor()

    # IN 절 + JOIN으로 1회 쿼리 — N+1 제거
    placeholders = ",".join("?" * len(user_ids))
    cursor.execute(
        f"""
        SELECT o.user_id, o.id, o.total, oi.product_name, oi.quantity
        FROM orders o
        JOIN order_items oi ON o.id = oi.order_id
        WHERE o.user_id IN ({placeholders})
        """,
        user_ids,
    )

    rows = cursor.fetchall()
    result = {}
    for row in rows:
        user_id = row[0]
        if user_id not in result:
            result[user_id] = []
        result[user_id].append(row)

    conn.close()
    return result


# ===== [Token Energy] LRU 캐싱 활용 =====
# 동일 텍스트 재호출 시 캐시에서 반환 — 토큰 소비 제거
@lru_cache(maxsize=256)
def generate_summary(text: str) -> str:
    """캐싱 활용 — Token Energy 효율적"""
    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        json={
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": f"Summarize: {text}"}],
        },
    )
    return response.json()


# ===== 전체 처리 — 효율적 패턴 결합 =====
def process_all_users():
    """3가지 에너지 효율 패턴이 적용된 처리 함수"""
    users = list(range(100))

    # 1. O(n) 해시 기반 — Compute 절약
    duplicates = find_duplicates(users)

    # 2. JOIN 1회 쿼리 — Data 절약
    orders = get_user_orders(users)

    # 3. 캐싱된 LLM 호출 — Token 절약
    for user_id, user_orders in orders.items():
        for order_data in user_orders:
            summary = generate_summary(str(order_data))
            print(summary)
