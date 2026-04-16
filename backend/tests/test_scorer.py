"""
점수 산출 + 근거 생성 테스트
==============================
STEP 3 검증: bad 코드 → D등급 이상 + 근거 3개 이상 출력

테스트 항목:
1. scorer.score() → ScoreReport 정상 생성
2. bad 코드: 높은 등급 + 근거 3건+ (compute+data+token)
3. good 코드: 낮은 등급 + 근거 적음
4. 3축 요약 (AxisSummary) 정합성
5. 종합 요약 텍스트 생성
"""
import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline.parser import parse_code
from pipeline.analyzer import analyze
from pipeline.scorer import score, ScoreReport, GRADE_INFO


# ================================================================
# 테스트용 코드 (test_analyzer.py와 동일)
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

EMPTY_CODE = ''


# ================================================================
# ScoreReport 기본 테스트
# ================================================================
class TestScoreReport:
    """scorer.score() 기본 동작 검증"""

    def test_score_returns_report(self):
        """score() → ScoreReport 타입 반환"""
        result = score(analyze(parse_code(BAD_CODE)))
        assert isinstance(result, ScoreReport)

    def test_score_has_sci_score(self):
        """SCI 점수 존재 + 양수"""
        report = score(analyze(parse_code(BAD_CODE)))
        assert report.sci_score > 0

    def test_score_has_grade(self):
        """등급 A~F 중 하나"""
        report = score(analyze(parse_code(BAD_CODE)))
        assert report.grade in ("A", "B", "C", "D", "F")

    def test_score_has_grade_info(self):
        """등급 라벨, 색상, 설명 존재"""
        report = score(analyze(parse_code(BAD_CODE)))
        assert report.grade_label != ""
        assert report.grade_color.startswith("#")
        assert report.grade_description != ""

    def test_score_has_summary_text(self):
        """종합 요약 텍스트 존재"""
        report = score(analyze(parse_code(BAD_CODE)))
        assert len(report.summary_text) > 0
        assert "SCI" in report.summary_text


# ================================================================
# Bad 코드 점수 검증 — ROADMAP 완료 기준
# ================================================================
class TestBadCodeScore:
    """ROADMAP 검증: bad 코드 → D등급 이상 + 근거 3개 이상"""

    def test_bad_code_high_grade(self):
        """★ bad 코드 → D 또는 F 등급"""
        report = score(analyze(parse_code(BAD_CODE)))
        assert report.grade in ("D", "F")

    def test_bad_code_findings_minimum_3(self):
        """★ bad 코드 → 근거(findings) 3건 이상"""
        report = score(analyze(parse_code(BAD_CODE)))
        assert len(report.findings) >= 3

    def test_bad_code_findings_cover_3_axes(self):
        """bad 코드 근거가 compute + data + token 3축 모두 포함"""
        report = score(analyze(parse_code(BAD_CODE)))
        axes = {f.axis for f in report.findings}
        assert "compute" in axes
        assert "data" in axes
        assert "token" in axes

    def test_bad_code_has_high_severity(self):
        """bad 코드에 high severity 발견 사항 존재"""
        report = score(analyze(parse_code(BAD_CODE)))
        high_findings = [f for f in report.findings if f.severity == "high"]
        assert len(high_findings) >= 1

    def test_bad_code_findings_have_suggestions(self):
        """모든 근거에 개선 제안(suggestion) 존재"""
        report = score(analyze(parse_code(BAD_CODE)))
        for finding in report.findings:
            assert finding.suggestion != ""

    def test_bad_code_findings_have_reduction(self):
        """모든 근거에 예상 절감(estimated_reduction) 존재"""
        report = score(analyze(parse_code(BAD_CODE)))
        for finding in report.findings:
            assert finding.estimated_reduction != ""

    def test_bad_code_findings_have_line_numbers(self):
        """모든 근거에 코드 줄 번호 존재"""
        report = score(analyze(parse_code(BAD_CODE)))
        for finding in report.findings:
            assert finding.line > 0

    def test_bad_code_findings_have_function_names(self):
        """모든 근거에 함수명 존재"""
        report = score(analyze(parse_code(BAD_CODE)))
        func_names = {f.function_name for f in report.findings}
        assert len(func_names) >= 2  # 최소 2개 함수에서 발견


# ================================================================
# Good 코드 점수 검증
# ================================================================
class TestGoodCodeScore:
    """good 코드 점수 검증"""

    def test_good_lower_than_bad(self):
        """good SCI < bad SCI"""
        bad_report = score(analyze(parse_code(BAD_CODE)))
        good_report = score(analyze(parse_code(GOOD_CODE)))
        assert good_report.sci_score < bad_report.sci_score

    def test_good_fewer_findings_than_bad(self):
        """good 근거 < bad 근거"""
        bad_report = score(analyze(parse_code(BAD_CODE)))
        good_report = score(analyze(parse_code(GOOD_CODE)))
        assert len(good_report.findings) < len(bad_report.findings)

    def test_good_no_high_severity_issues(self):
        """good 코드에 high severity 없음 (캐싱 적용됨)"""
        report = score(analyze(parse_code(GOOD_CODE)))
        high_findings = [f for f in report.findings if f.severity == "high"]
        assert len(high_findings) == 0


# ================================================================
# 3축 요약 (AxisSummary) 테스트
# ================================================================
class TestAxisSummary:
    """AxisSummary 정합성 검증"""

    def test_axis_count_is_3(self):
        """3축 요약이 정확히 3개"""
        report = score(analyze(parse_code(BAD_CODE)))
        assert len(report.axis_summaries) == 3

    def test_axis_names(self):
        """3축 이름: compute, data, token"""
        report = score(analyze(parse_code(BAD_CODE)))
        axes = [s.axis for s in report.axis_summaries]
        assert "compute" in axes
        assert "data" in axes
        assert "token" in axes

    def test_axis_percentages_sum_100(self):
        """3축 비율 합 = 100%"""
        report = score(analyze(parse_code(BAD_CODE)))
        total_pct = sum(s.percentage for s in report.axis_summaries)
        assert abs(total_pct - 100.0) < 0.5  # 반올림 허용

    def test_bad_code_token_dominant(self):
        """bad 코드: Token 축이 지배적 (캐싱 없는 LLM 1000회 호출)"""
        report = score(analyze(parse_code(BAD_CODE)))
        token_summary = next(s for s in report.axis_summaries if s.axis == "token")
        assert token_summary.percentage > 90  # Token이 90%+ 차지

    def test_axis_status_values(self):
        """status는 good/warning/critical 중 하나"""
        report = score(analyze(parse_code(BAD_CODE)))
        for summary in report.axis_summaries:
            assert summary.status in ("good", "warning", "critical")


# ================================================================
# 빈 코드 + 엣지 케이스
# ================================================================
class TestEdgeCases:
    """엣지 케이스 테스트"""

    def test_empty_code_a_grade(self):
        """빈 코드 → A등급, 근거 0건"""
        report = score(analyze(parse_code(EMPTY_CODE)))
        assert report.grade == "A"
        assert len(report.findings) == 0

    def test_empty_code_summary_exists(self):
        """빈 코드도 요약 텍스트 생성"""
        report = score(analyze(parse_code(EMPTY_CODE)))
        assert len(report.summary_text) > 0

    def test_grade_info_all_exist(self):
        """GRADE_INFO에 A~F 모두 정의됨"""
        for grade in ("A", "B", "C", "D", "F"):
            assert grade in GRADE_INFO
            info = GRADE_INFO[grade]
            assert "label" in info
            assert "color" in info
            assert "description" in info
