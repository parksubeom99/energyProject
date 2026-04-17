"""
최적화 + 검증 테스트
=====================
STEP 6 검증: Before/After SCI 비교 — 최적화 후 점수 감소 실증

테스트 항목:
1. MockClaudeClient 규칙 기반 최적화
2. 최적화 코드 문법 유효성
3. ★ Before > After SCI (핵심 검증)
4. 감소율 계산
5. 적용된 수정 목록 식별
6. verifier Before/After 검증
"""
import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline.parser import parse_code
from pipeline.analyzer import analyze
from pipeline.scorer import score
from pipeline.optimizer import (
    optimize, MockClaudeClient, OptimizationResult,
    _validate_syntax, _build_optimization_prompt,
)
from pipeline.verifier import verify, VerificationResult


# ================================================================
# 테스트용 코드 — sample_bad.py 패턴
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

SIMPLE_CODE = '''
import requests

def summarize(text):
    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        json={"model": "claude-sonnet-4-20250514", "messages": [{"role": "user", "content": text}]},
    )
    return response.json()
'''

GOOD_CODE = '''
from functools import lru_cache

def find_duplicates(items: list) -> list:
    seen = set()
    duplicates = set()
    for item in items:
        if item in seen:
            duplicates.add(item)
        seen.add(item)
    return list(duplicates)
'''


# ================================================================
# MockClaudeClient 테스트
# ================================================================
class TestMockClaudeClient:
    def test_mock_generates_valid_code(self):
        """Mock이 생성한 코드가 문법적으로 유효"""
        report = score(analyze(parse_code(BAD_CODE)))
        result = optimize(report, BAD_CODE, client=MockClaudeClient())
        assert result.is_valid
        is_valid, _ = _validate_syntax(result.optimized_code)
        assert is_valid

    def test_mock_adds_lru_cache(self):
        """Mock이 @lru_cache를 추가"""
        report = score(analyze(parse_code(SIMPLE_CODE)))
        result = optimize(report, SIMPLE_CODE, client=MockClaudeClient())
        assert "@lru_cache" in result.optimized_code

    def test_mock_converts_nested_loop(self):
        """Mock이 중첩 루프를 set 기반으로 변환"""
        report = score(analyze(parse_code(BAD_CODE)))
        result = optimize(report, BAD_CODE, client=MockClaudeClient())
        assert "seen = set()" in result.optimized_code

    def test_mock_identifies_applied_fixes(self):
        """적용된 수정 목록이 존재"""
        report = score(analyze(parse_code(BAD_CODE)))
        result = optimize(report, BAD_CODE, client=MockClaudeClient())
        assert len(result.applied_fixes) >= 1


# ================================================================
# 최적화 함수 테스트
# ================================================================
class TestOptimize:
    def test_optimize_returns_result(self):
        """optimize() → OptimizationResult 타입"""
        report = score(analyze(parse_code(BAD_CODE)))
        result = optimize(report, BAD_CODE, client=MockClaudeClient())
        assert isinstance(result, OptimizationResult)

    def test_optimize_has_original_and_optimized(self):
        """원본 + 최적화 코드 모두 존재"""
        report = score(analyze(parse_code(BAD_CODE)))
        result = optimize(report, BAD_CODE, client=MockClaudeClient())
        assert result.original_code == BAD_CODE
        assert len(result.optimized_code) > 0
        assert result.original_code != result.optimized_code

    def test_optimize_already_good_code(self):
        """이미 좋은 코드 → 변화 최소"""
        report = score(analyze(parse_code(GOOD_CODE)))
        result = optimize(report, GOOD_CODE, client=MockClaudeClient())
        assert result.is_valid

    def test_prompt_contains_findings(self):
        """프롬프트에 findings가 포함됨"""
        report = score(analyze(parse_code(BAD_CODE)))
        prompt = _build_optimization_prompt(report, BAD_CODE)
        assert "SCI" in prompt
        assert "compute" in prompt or "data" in prompt or "token" in prompt


# ================================================================
# ★ Before/After SCI 검증 — STEP 6 핵심
# ================================================================
class TestVerifier:
    def test_verify_returns_result(self):
        """verify() → VerificationResult 타입"""
        report = score(analyze(parse_code(BAD_CODE)))
        opt = optimize(report, BAD_CODE, client=MockClaudeClient())
        result = verify(opt)
        assert isinstance(result, VerificationResult)

    def test_before_after_sci_improved(self):
        """★ 핵심: After SCI < Before SCI (최적화 효과 실증)"""
        report = score(analyze(parse_code(BAD_CODE)))
        opt = optimize(report, BAD_CODE, client=MockClaudeClient())
        result = verify(opt)
        assert result.is_improved
        assert result.after_sci < result.before_sci
        assert result.status == "verified"

    def test_sci_reduction_positive(self):
        """SCI 감소량/감소율이 양수"""
        report = score(analyze(parse_code(BAD_CODE)))
        opt = optimize(report, BAD_CODE, client=MockClaudeClient())
        result = verify(opt)
        assert result.sci_reduction > 0
        assert result.sci_reduction_pct > 0

    def test_sci_reduction_significant(self):
        """★ 감소율이 유의미 (10% 이상)"""
        report = score(analyze(parse_code(BAD_CODE)))
        opt = optimize(report, BAD_CODE, client=MockClaudeClient())
        result = verify(opt)
        assert result.sci_reduction_pct >= 10, \
            f"감소율 {result.sci_reduction_pct}%가 10% 미만"

    def test_before_grade_worse_than_after(self):
        """Before 등급이 After 등급보다 나쁨 (또는 같음)"""
        report = score(analyze(parse_code(BAD_CODE)))
        opt = optimize(report, BAD_CODE, client=MockClaudeClient())
        result = verify(opt)
        grade_order = {"A": 0, "B": 1, "C": 2, "D": 3, "F": 4}
        assert grade_order[result.before_grade] >= grade_order[result.after_grade]

    def test_verify_invalid_optimization(self):
        """최적화 실패 시 status="failed" """
        opt = OptimizationResult(
            original_code=BAD_CODE,
            optimized_code="",
            is_valid=False,
            error_message="API 오류",
        )
        result = verify(opt)
        assert result.status == "failed"
        assert not result.is_improved

    def test_verify_with_custom_region(self):
        """다른 지역(프랑스)에서도 검증 동작"""
        report = score(analyze(parse_code(BAD_CODE)))
        opt = optimize(report, BAD_CODE, client=MockClaudeClient())
        result = verify(opt, carbon_intensity=60)  # 프랑스
        assert result.before_sci > 0
        assert result.after_sci > 0

    def test_applied_fixes_in_verification(self):
        """검증 결과에 적용된 수정 목록 포함"""
        report = score(analyze(parse_code(BAD_CODE)))
        opt = optimize(report, BAD_CODE, client=MockClaudeClient())
        result = verify(opt)
        assert len(result.applied_fixes) >= 1
