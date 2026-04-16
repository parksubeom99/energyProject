"""
파서 + 분석기 테스트
=====================
STEP 2 검증: 샘플 코드 3종(bad/good/mixed) 분석 결과 출력

테스트 항목:
1. parser.py — AST 파싱, 함수 추출, 루프/DB/API/LLM 호출 탐지
2. analyzer.py — 3축 에너지 추정 + SCI 점수 산출
3. 샘플 코드 비교: bad > mixed > good (에너지 순)
"""
import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline.parser import parse_code, ParseResult
from pipeline.analyzer import analyze, AnalysisResult


# ================================================================
# 테스트용 코드 스니펫
# ================================================================
BAD_CODE = '''
import sqlite3
import requests

def find_duplicates(items: list) -> list:
    duplicates = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if items[i] == items[j]:
                if items[i] not in duplicates:
                    duplicates.append(items[i])
    return duplicates

def get_user_orders(user_ids: list) -> dict:
    conn = sqlite3.connect("shop.db")
    cursor = conn.cursor()
    result = {}
    for user_id in user_ids:
        cursor.execute("SELECT * FROM orders WHERE user_id = ?", (user_id,))
        orders = cursor.fetchall()
        for order in orders:
            cursor.execute("SELECT * FROM order_items WHERE order_id = ?", (order[0],))
            items = cursor.fetchall()
            if user_id not in result:
                result[user_id] = []
            result[user_id].append({"order": order, "items": items})
    conn.close()
    return result

def generate_summary(text: str) -> str:
    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        json={"model": "claude-sonnet-4-20250514", "messages": [{"role": "user", "content": text}]},
    )
    return response.json()
'''

GOOD_CODE = '''
import sqlite3
from functools import lru_cache
import requests

def find_duplicates(items: list) -> list:
    seen = set()
    duplicates = set()
    for item in items:
        if item in seen:
            duplicates.add(item)
        seen.add(item)
    return list(duplicates)

def get_user_orders(user_ids: list) -> dict:
    conn = sqlite3.connect("shop.db")
    cursor = conn.cursor()
    placeholders = ",".join("?" * len(user_ids))
    cursor.execute(f"SELECT o.user_id, o.id FROM orders o WHERE o.user_id IN ({placeholders})", user_ids)
    rows = cursor.fetchall()
    result = {}
    for row in rows:
        user_id = row[0]
        if user_id not in result:
            result[user_id] = []
        result[user_id].append(row)
    conn.close()
    return result

@lru_cache(maxsize=256)
def generate_summary(text: str) -> str:
    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        json={"model": "claude-sonnet-4-20250514", "messages": [{"role": "user", "content": text}]},
    )
    return response.json()
'''

MIXED_CODE = '''
import sqlite3

def find_active_users(users: list) -> list:
    active_ids = set()
    active_users = []
    for user in users:
        if user.get("is_active") and user["id"] not in active_ids:
            active_ids.add(user["id"])
            active_users.append(user)
    return active_users

def get_user_profiles(user_ids: list) -> list:
    conn = sqlite3.connect("app.db")
    cursor = conn.cursor()
    profiles = []
    for user_id in user_ids:
        cursor.execute("SELECT * FROM profiles WHERE user_id = ?", (user_id,))
        profile = cursor.fetchone()
        if profile:
            cursor.execute("SELECT * FROM settings WHERE user_id = ?", (user_id,))
            settings = cursor.fetchone()
            profiles.append({"profile": profile, "settings": settings})
    conn.close()
    return profiles

def format_report(data: dict) -> str:
    lines = []
    for key, value in data.items():
        lines.append(f"  {key}: {value}")
    return chr(10).join(lines)
'''


# ================================================================
# Parser 테스트 — AST 파싱
# ================================================================
class TestParser:
    """parser.py 단위 테스트"""

    def test_parse_bad_code_functions(self):
        """bad 코드에서 3개 함수 추출"""
        result = parse_code(BAD_CODE)
        assert len(result.functions) == 3
        names = [f.name for f in result.functions]
        assert "find_duplicates" in names
        assert "get_user_orders" in names
        assert "generate_summary" in names

    def test_parse_bad_code_nested_loops(self):
        """find_duplicates: 중첩 루프 depth 2 탐지"""
        result = parse_code(BAD_CODE)
        dup_func = next(f for f in result.functions if f.name == "find_duplicates")
        assert dup_func.nested_loop_depth == 2
        assert dup_func.loop_count >= 2

    def test_parse_bad_code_db_calls(self):
        """get_user_orders: N+1 DB 호출 탐지"""
        result = parse_code(BAD_CODE)
        orders_func = next(f for f in result.functions if f.name == "get_user_orders")
        execute_calls = [c for c in orders_func.db_calls if c["method"] == "execute"]
        assert len(execute_calls) >= 2  # 최소 2개 개별 execute

    def test_parse_bad_code_llm_url_reclassified(self):
        """generate_summary: anthropic.com URL → LLM 호출로 재분류"""
        result = parse_code(BAD_CODE)
        summary_func = next(f for f in result.functions if f.name == "generate_summary")
        # requests.post("https://api.anthropic.com/...") → LLM으로 재분류됨
        assert len(summary_func.llm_calls) >= 1
        # API 호출에서는 제거됨
        assert len(summary_func.api_calls) == 0

    def test_parse_good_code_llm_url_reclassified(self):
        """good 코드도 LLM URL 재분류 동작"""
        result = parse_code(GOOD_CODE)
        summary_func = next(f for f in result.functions if f.name == "generate_summary")
        assert len(summary_func.llm_calls) >= 1

    def test_parse_good_code_cache_decorator(self):
        """good 코드: @lru_cache 데코레이터 탐지"""
        result = parse_code(GOOD_CODE)
        summary_func = next(f for f in result.functions if f.name == "generate_summary")
        assert summary_func.has_cache_decorator is True

    def test_parse_bad_code_no_cache(self):
        """bad 코드: 캐시 데코레이터 없음"""
        result = parse_code(BAD_CODE)
        summary_func = next(f for f in result.functions if f.name == "generate_summary")
        assert summary_func.has_cache_decorator is False

    def test_parse_good_code_single_loop(self):
        """good 코드: 단일 루프 (depth 1)"""
        result = parse_code(GOOD_CODE)
        dup_func = next(f for f in result.functions if f.name == "find_duplicates")
        assert dup_func.nested_loop_depth == 1

    def test_parse_good_code_single_query(self):
        """good 코드: JOIN 1회 쿼리"""
        result = parse_code(GOOD_CODE)
        orders_func = next(f for f in result.functions if f.name == "get_user_orders")
        execute_calls = [c for c in orders_func.db_calls if c["method"] == "execute"]
        assert len(execute_calls) == 1  # JOIN 1회

    def test_parse_mixed_code_functions(self):
        """mixed 코드에서 3개 함수 추출"""
        result = parse_code(MIXED_CODE)
        assert len(result.functions) == 3

    def test_parse_syntax_error(self):
        """문법 오류 코드 → errors 리스트에 기록"""
        result = parse_code("def broken(:\n  pass")
        assert len(result.errors) > 0

    def test_parse_empty_code(self):
        """빈 코드 → 함수 0개, 오류 없음"""
        result = parse_code("")
        assert len(result.functions) == 0
        assert len(result.errors) == 0

    def test_cyclomatic_complexity(self):
        """순환 복잡도: 분기+루프가 많으면 높음"""
        result = parse_code(BAD_CODE)
        dup_func = next(f for f in result.functions if f.name == "find_duplicates")
        # CC = 1 + branches + loops >= 5 (for+for+if+if = 루프2+분기2 → CC 5+)
        assert dup_func.cyclomatic_complexity >= 5


# ================================================================
# Analyzer 테스트 — 3축 에너지 분석
# ================================================================
class TestAnalyzer:
    """analyzer.py 단위 테스트 (기본값: functional_unit=1, executions=1000)"""

    def test_bad_sci_score_higher_than_good(self):
        """★ 핵심 검증: bad SCI 점수 > good SCI 점수 (동일 조건)"""
        bad_result = analyze(parse_code(BAD_CODE))
        good_result = analyze(parse_code(GOOD_CODE))
        assert bad_result.sci_result.sci_score > good_result.sci_result.sci_score

    def test_bad_and_good_sci_score_gap(self):
        """bad와 good의 SCI 점수 차이가 유의미 (M=0으로 에너지만 비교)"""
        # M=0으로 내재 탄소 제거 → 순수 에너지 기반 점수 비교
        bad_result = analyze(parse_code(BAD_CODE), embodied_carbon=0)
        good_result = analyze(parse_code(GOOD_CODE), embodied_carbon=0)
        # bad의 Compute Energy가 중첩루프로 10배+ 높음
        assert bad_result.sci_result.sci_score > good_result.sci_result.sci_score * 1.1

    def test_bad_energy_higher_than_good(self):
        """bad 에너지 > good 에너지 (3축 합산)"""
        bad_result = analyze(parse_code(BAD_CODE))
        good_result = analyze(parse_code(GOOD_CODE))
        assert bad_result.energy_breakdown.total_energy_kwh > \
               good_result.energy_breakdown.total_energy_kwh

    def test_mixed_issues_fewer_than_bad(self):
        """mixed: 이슈 있지만 bad보다 적음"""
        bad_result = analyze(parse_code(BAD_CODE))
        mixed_result = analyze(parse_code(MIXED_CODE))
        assert len(mixed_result.issues) < len(bad_result.issues)
        assert mixed_result.max_nested_depth < bad_result.max_nested_depth

    def test_bad_code_issues_detected(self):
        """bad 코드에서 비효율 이슈 탐지 (중첩루프 + N+1 + 캐싱없는 LLM)"""
        result = analyze(parse_code(BAD_CODE))
        assert len(result.issues) >= 3
        issue_types = [i["type"] for i in result.issues]
        assert "compute" in issue_types   # O(n²) 탐지
        assert "data" in issue_types      # N+1 탐지
        assert "token" in issue_types     # 캐싱 없는 LLM 호출 탐지

    def test_bad_code_has_token_energy(self):
        """bad 코드: LLM URL 탐지 → Token Energy > 0"""
        result = analyze(parse_code(BAD_CODE))
        assert result.energy_breakdown.token_energy_kwh > 0
        assert result.total_llm_calls >= 1

    def test_good_code_minimal_issues(self):
        """good 코드에서 이슈가 bad보다 적음"""
        result = analyze(parse_code(GOOD_CODE))
        bad_result = analyze(parse_code(BAD_CODE))
        assert len(result.issues) < len(bad_result.issues)

    def test_energy_breakdown_3_axes(self):
        """3축 에너지 브레이크다운 존재"""
        result = analyze(parse_code(BAD_CODE))
        eb = result.energy_breakdown
        assert eb.compute_energy_kwh > 0
        assert eb.data_energy_kwh > 0
        assert eb.token_energy_kwh > 0   # LLM URL 탐지로 0이 아님
        assert eb.total_energy_kwh > 0

    def test_function_analyses_count(self):
        """함수별 분석 결과 개수 = 함수 수"""
        result = analyze(parse_code(BAD_CODE))
        assert result.total_functions == 3
        assert len(result.function_analyses) == 3

    def test_custom_carbon_intensity(self):
        """탄소 강도 변경 시 SCI 점수 변화"""
        parsed = parse_code(BAD_CODE)
        korea = analyze(parsed, carbon_intensity=450, embodied_carbon=0)
        france = analyze(parsed, carbon_intensity=60, embodied_carbon=0)
        assert france.sci_result.sci_score < korea.sci_result.sci_score

    def test_empty_code_analysis(self):
        """빈 코드 → 정상 분석 (에너지 ≈ 0, 등급 A)"""
        result = analyze(parse_code(""))
        assert result.sci_result.grade == "A"
        assert result.total_functions == 0

    def test_analysis_summary_stats(self):
        """요약 통계 필드 정합성"""
        result = analyze(parse_code(BAD_CODE))
        assert result.total_lines > 0
        assert result.total_db_calls >= 2
        assert result.total_llm_calls >= 1  # LLM URL 재분류 반영
        assert result.max_nested_depth >= 2
