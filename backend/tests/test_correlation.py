"""
핵심 가설 검증: Pearson r > 0.7
==================================
"코드 정적 분석으로 추정한 SCI 점수와
 실제 에너지 패턴의 상관계수가 0.7 이상이면
 정적 분석만으로 실용적 탄소 추정이 가능하다"

검증 방법:
- 다양한 패턴의 코드 스니펫을 준비
- 각각의 "예상 에너지 등급"(전문가 라벨)을 설정
- 정적 분석 SCI 점수와 예상 등급 간 Pearson 상관계수 계산
- assert r > 0.7

면접 포인트:
"핵심 가설을 pytest로 CI에서 자동 검증합니다.
 Pearson r > 0.7이면 정적 분석 추정이 실용적이라는 뜻이고,
 실패하면 동적 프로파일링 병행 모드를 투입합니다."
"""
import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline.parser import parse_code
from pipeline.analyzer import analyze


# ================================================================
# 테스트 코드 + 전문가 라벨 (예상 에너지 등급)
# ================================================================
# 각 코드의 에너지 수준을 1(최소)~5(최대)로 라벨링.
# 정적 분석 SCI 점수와 이 라벨 간 상관관계를 검증.

TEST_CASES = [
    # (라벨, 코드) — 라벨이 높을수록 에너지 소비 큼
    (1, "x = 1"),  # 최소 에너지
    (1, "def f(x): return x + 1"),  # 단순 함수
    (2, """
def search(items, target):
    for item in items:
        if item == target:
            return True
    return False
"""),  # 단일 루프 O(n)
    (3, """
import sqlite3
def get_data(ids):
    conn = sqlite3.connect("db")
    cursor = conn.cursor()
    for id in ids:
        cursor.execute("SELECT * FROM t WHERE id=?", (id,))
    conn.close()
"""),  # N+1 쿼리
    (4, """
def bubble_sort(arr):
    n = len(arr)
    for i in range(n):
        for j in range(0, n-i-1):
            if arr[j] > arr[j+1]:
                arr[j], arr[j+1] = arr[j+1], arr[j]
    return arr
"""),  # O(n²) 중첩 루프
    (5, """
import requests
def process(data_list):
    results = []
    for item in data_list:
        for sub in item:
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                json={"model": "claude-sonnet-4-20250514", "messages": [{"role": "user", "content": str(sub)}]},
            )
            results.append(response.json())
    return results
"""),  # O(n²) + 캐싱 없는 LLM = 최악
]


# ================================================================
# Pearson 상관계수 계산 (scipy 없이 순수 Python)
# ================================================================
def pearson_r(x: list[float], y: list[float]) -> float:
    """
    Pearson 상관계수 계산

    scipy.stats.pearsonr와 동일한 결과.
    Docker 환경에서 scipy 설치 없이 동작하도록 순수 Python 구현.
    """
    n = len(x)
    assert n == len(y) and n > 2

    mean_x = sum(x) / n
    mean_y = sum(y) / n

    cov = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
    std_x = (sum((xi - mean_x) ** 2 for xi in x)) ** 0.5
    std_y = (sum((yi - mean_y) ** 2 for yi in y)) ** 0.5

    if std_x == 0 or std_y == 0:
        return 0.0

    return cov / (std_x * std_y)


# ================================================================
# 핵심 가설 테스트
# ================================================================
class TestCorrelation:
    """정적 분석 SCI vs 전문가 라벨 상관관계"""

    def test_pearson_r_above_0_7(self):
        """★ 핵심 가설: Pearson r > 0.7"""
        labels = []
        sci_scores = []

        for label, code in TEST_CASES:
            parsed = parse_code(code)
            result = analyze(parsed, embodied_carbon=0)
            labels.append(float(label))
            sci_scores.append(result.sci_result.sci_score)

        r = pearson_r(labels, sci_scores)
        print(f"\n=== Pearson r = {r:.4f} ===")
        for i, (label, code) in enumerate(TEST_CASES):
            print(f"  Label {label} → SCI {sci_scores[i]:.4f}")

        assert r > 0.7, f"Pearson r = {r:.4f} < 0.7 — 가설 실패"

    def test_monotonic_ordering(self):
        """에너지 라벨이 높을수록 SCI도 높음 (단조 증가 경향)"""
        scores_by_label = {}
        for label, code in TEST_CASES:
            parsed = parse_code(code)
            result = analyze(parsed, embodied_carbon=0)
            if label not in scores_by_label:
                scores_by_label[label] = []
            scores_by_label[label].append(result.sci_result.sci_score)

        # 각 라벨의 평균 SCI
        avg_scores = {
            label: sum(s) / len(s) for label, s in scores_by_label.items()
        }
        sorted_labels = sorted(avg_scores.keys())

        # 라벨 1의 평균 < 라벨 5의 평균
        assert avg_scores[sorted_labels[0]] < avg_scores[sorted_labels[-1]], \
            "최소 라벨(1)의 SCI가 최대 라벨(5)보다 높음"

    def test_extreme_cases_distinguishable(self):
        """극단 케이스: 최소(라벨1) vs 최대(라벨5) SCI 차이가 10배+"""
        min_code = TEST_CASES[0][1]  # 라벨 1
        max_code = TEST_CASES[-1][1]  # 라벨 5

        min_sci = analyze(parse_code(min_code), embodied_carbon=0).sci_result.sci_score
        max_sci = analyze(parse_code(max_code), embodied_carbon=0).sci_result.sci_score

        ratio = max_sci / max(min_sci, 1e-10)
        assert ratio > 10, f"최대/최소 비율 {ratio:.1f}x < 10x"
