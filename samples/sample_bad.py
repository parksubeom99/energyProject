"""
GreenPulse 테스트용 샘플 코드 — "나쁜" 패턴
=============================================
이 코드는 의도적으로 에너지 비효율 패턴을 포함합니다.
SCI 점수: 예상 D등급 (50~100 gCO2eq/R)

포함된 비효율 패턴:
1. [Compute] O(n^2) 중첩 루프 — CPU 연산 낭비
2. [Data]    N+1 쿼리 패턴 — DB IO 낭비
3. [Token]   매 요청마다 LLM API 호출 — 토큰 에너지 낭비
"""
import sqlite3
import requests


# ===== [Compute Energy] O(n^2) 중첩 루프 =====
# 문제: 이중 루프로 중복 탐지 → O(n^2) 시간 복잡도
# 개선: set 기반 O(n) 탐지로 변환 가능
def find_duplicates(items: list) -> list:
    """O(n^2) 중첩 루프 — Compute Energy 낭비"""
    duplicates = []
    for i in range(len(items)):                    # 외부 루프: n회
        for j in range(i + 1, len(items)):         # 내부 루프: n-1회
            if items[i] == items[j]:               # 비교 연산
                if items[i] not in duplicates:     # 또 다시 선형 탐색!
                    duplicates.append(items[i])
    return duplicates


# ===== [Data Energy] N+1 쿼리 패턴 =====
# 문제: 유저 N명 × 주문 M건 × 아이템 K건 = N×M+N개 쿼리
# 개선: JOIN 1회 쿼리로 변환 가능
def get_user_orders(user_ids: list) -> dict:
    """N+1 쿼리 패턴 — Data Energy 낭비"""
    conn = sqlite3.connect("shop.db")
    cursor = conn.cursor()

    result = {}
    for user_id in user_ids:
        # 1차 N+1: 유저마다 개별 SELECT
        cursor.execute(
            "SELECT * FROM orders WHERE user_id = ?", (user_id,)
        )
        orders = cursor.fetchall()

        for order in orders:
            # 2차 N+1: 주문마다 또 개별 SELECT (중첩 N+1)
            cursor.execute(
                "SELECT * FROM order_items WHERE order_id = ?", (order[0],)
            )
            items = cursor.fetchall()

            if user_id not in result:
                result[user_id] = []
            result[user_id].append({"order": order, "items": items})

    conn.close()
    return result


# ===== [Token Energy] 캐싱 없는 LLM 호출 =====
# 문제: 동일 텍스트도 매번 API 호출 → 불필요한 토큰 소비
# 개선: lru_cache 또는 Redis 캐싱으로 중복 호출 제거
def generate_summary(text: str) -> str:
    """매 요청마다 LLM 호출 — Token Energy 낭비"""
    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        json={
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": f"Summarize: {text}"}],
        },
    )
    return response.json()


# ===== 전체 처리 — 3가지 비효율 패턴 결합 =====
def process_all_users():
    """3가지 에너지 비효율 패턴이 결합된 처리 함수"""
    users = list(range(100))

    # 1. O(n^2) 중복 찾기 — Compute 낭비
    duplicates = find_duplicates(users)

    # 2. N+1 쿼리 — Data 낭비
    orders = get_user_orders(users)

    # 3. 매번 LLM 호출 — Token 낭비
    for user_id, user_orders in orders.items():
        for order_data in user_orders:
            summary = generate_summary(str(order_data))
            print(summary)
