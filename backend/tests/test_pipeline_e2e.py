"""
전체 파이프라인 E2E 테스트
===========================
STEP 10 검증: 코드 업로드 → SCI 점수 → 최적화 → Before/After

파이프라인 5단계를 처음부터 끝까지 통합 검증:
  ① Parser → ② Analyzer → ③ Scorer → ④ Optimizer → ⑤ Verifier
"""
import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline.parser import parse_code
from pipeline.analyzer import analyze
from pipeline.scorer import score
from pipeline.optimizer import optimize, MockClaudeClient
from pipeline.verifier import verify


# ================================================================
# 테스트용 전체 코드
# ================================================================
FULL_BAD_CODE = '''
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


# ================================================================
# E2E: 전체 파이프라인 통합 테스트
# ================================================================
class TestE2EPipeline:
    """코드 → Parser → Analyzer → Scorer → Optimizer → Verifier"""

    def test_full_pipeline_e2e(self):
        """★ 전체 5단계 E2E: 코드 입력 → Before/After SCI 비교 검증"""
        # ① Parser
        parsed = parse_code(FULL_BAD_CODE)
        assert len(parsed.functions) == 3
        assert len(parsed.errors) == 0

        # ② Analyzer
        analysis = analyze(parsed)
        assert analysis.sci_result.sci_score > 0
        assert analysis.total_functions == 3

        # ③ Scorer
        report = score(analysis)
        assert report.grade in ("D", "F")
        assert len(report.findings) >= 3

        # ④ Optimizer
        opt = optimize(report, FULL_BAD_CODE, client=MockClaudeClient())
        assert opt.is_valid
        assert opt.optimized_code != FULL_BAD_CODE

        # ⑤ Verifier
        vr = verify(opt)
        assert vr.is_improved
        assert vr.after_sci < vr.before_sci
        assert vr.sci_reduction_pct > 0
        assert vr.status == "verified"

    def test_e2e_sci_reduction_significant(self):
        """E2E: SCI 감소율이 50% 이상"""
        parsed = parse_code(FULL_BAD_CODE)
        report = score(analyze(parsed))
        opt = optimize(report, FULL_BAD_CODE, client=MockClaudeClient())
        vr = verify(opt)
        assert vr.sci_reduction_pct > 50, \
            f"감소율 {vr.sci_reduction_pct}%가 50% 미만"

    def test_e2e_grade_improvement(self):
        """E2E: Before 등급이 After보다 나쁨"""
        parsed = parse_code(FULL_BAD_CODE)
        report = score(analyze(parsed))
        opt = optimize(report, FULL_BAD_CODE, client=MockClaudeClient())
        vr = verify(opt)
        grade_order = {"A": 0, "B": 1, "C": 2, "D": 3, "F": 4}
        assert grade_order[vr.before_grade] > grade_order[vr.after_grade]

    def test_e2e_findings_3_axes(self):
        """E2E: 근거가 compute + data + token 3축 모두 포함"""
        parsed = parse_code(FULL_BAD_CODE)
        report = score(analyze(parsed))
        axes = {f.axis for f in report.findings}
        assert "compute" in axes
        assert "data" in axes
        assert "token" in axes

    def test_e2e_summary_text_readable(self):
        """E2E: 요약 텍스트에 SCI 점수 + 등급 + 원인 포함"""
        parsed = parse_code(FULL_BAD_CODE)
        report = score(analyze(parsed))
        assert "SCI" in report.summary_text
        assert report.grade in report.summary_text

    def test_e2e_axis_percentages_sum_100(self):
        """E2E: 3축 비율 합 ≈ 100%"""
        parsed = parse_code(FULL_BAD_CODE)
        report = score(analyze(parsed))
        total_pct = sum(s.percentage for s in report.axis_summaries)
        assert abs(total_pct - 100.0) < 0.5

    def test_e2e_optimized_code_valid_python(self):
        """E2E: 최적화 코드가 유효한 Python"""
        import ast as stdlib_ast
        parsed = parse_code(FULL_BAD_CODE)
        report = score(analyze(parsed))
        opt = optimize(report, FULL_BAD_CODE, client=MockClaudeClient())
        # 문법 검증
        stdlib_ast.parse(opt.optimized_code)

    def test_e2e_applied_fixes_recorded(self):
        """E2E: 적용된 수정 목록이 기록됨"""
        parsed = parse_code(FULL_BAD_CODE)
        report = score(analyze(parsed))
        opt = optimize(report, FULL_BAD_CODE, client=MockClaudeClient())
        vr = verify(opt)
        assert len(vr.applied_fixes) >= 1
