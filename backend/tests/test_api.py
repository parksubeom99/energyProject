"""
FastAPI + JWT + RBAC 테스트
============================
STEP 4 검증: curl로 분석 요청 → SCI 점수 + 근거 JSON 응답

테스트 항목:
1. 헬스체크
2. 로그인 → JWT 발급
3. JWT 인증된 분석 요청 → SCI 결과
4. Refresh Token Rotation
5. Rate Limiting (free: 5회 제한)
6. 인증 실패 케이스
"""
import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient
from main import app
from auth.jwt_handler import clear_blacklist
from auth.rbac import clear_all_usage
from events.kafka_consumer import clear_results


# ================================================================
# 테스트 클라이언트 + 픽스처
# ================================================================
client = TestClient(app)

BAD_CODE = '''
import sqlite3
import requests

def find_duplicates(items):
    duplicates = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if items[i] == items[j]:
                duplicates.append(items[i])
    return duplicates

def get_orders(user_ids):
    conn = sqlite3.connect("shop.db")
    cursor = conn.cursor()
    for uid in user_ids:
        cursor.execute("SELECT * FROM orders WHERE user_id = ?", (uid,))
        cursor.execute("SELECT * FROM items WHERE user_id = ?", (uid,))
    conn.close()

def summarize(text):
    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        json={"model": "claude-sonnet-4-20250514", "messages": [{"role": "user", "content": text}]},
    )
    return response.json()
'''


@pytest.fixture(autouse=True)
def cleanup():
    """각 테스트 전후 상태 초기화"""
    clear_blacklist()
    clear_all_usage()
    clear_results()
    yield
    clear_blacklist()
    clear_all_usage()
    clear_results()


def _login(username="admin", password="greenpulse") -> dict:
    """헬퍼: 로그인 후 토큰 반환"""
    resp = client.post("/auth/token", json={
        "username": username, "password": password,
    })
    assert resp.status_code == 200
    return resp.json()


def _auth_header(token: str) -> dict:
    """헬퍼: Authorization 헤더"""
    return {"Authorization": f"Bearer {token}"}


# ================================================================
# 헬스체크 테스트
# ================================================================
class TestHealth:
    def test_health_ok(self):
        """GET /health → 200"""
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    def test_health_has_version(self):
        """헬스체크에 앱 이름+버전 포함"""
        resp = client.get("/health")
        data = resp.json()
        assert data["app"] == "GreenPulse"
        assert "version" in data


# ================================================================
# 인증 테스트 — JWT 발급/갱신
# ================================================================
class TestAuth:
    def test_login_success(self):
        """admin 로그인 성공 → JWT 발급"""
        tokens = _login("admin", "greenpulse")
        assert "access_token" in tokens
        assert "refresh_token" in tokens
        assert tokens["token_type"] == "bearer"
        assert tokens["role"] == "admin"

    def test_login_wrong_password(self):
        """잘못된 비밀번호 → 401"""
        resp = client.post("/auth/token", json={
            "username": "admin", "password": "wrong",
        })
        assert resp.status_code == 401

    def test_login_unknown_user(self):
        """존재하지 않는 사용자 → 401"""
        resp = client.post("/auth/token", json={
            "username": "nobody", "password": "test",
        })
        assert resp.status_code == 401

    def test_refresh_token_rotation(self):
        """★ RTR: refresh → 새 토큰 쌍 + 기존 refresh 블랙리스트"""
        tokens = _login()
        old_refresh = tokens["refresh_token"]

        # 1차 갱신: 성공
        resp = client.post("/auth/refresh", json={
            "refresh_token": old_refresh,
        })
        assert resp.status_code == 200
        new_tokens = resp.json()
        assert new_tokens["access_token"] != tokens["access_token"]
        assert new_tokens["refresh_token"] != old_refresh

        # 2차 갱신 (같은 토큰): RTR 위반 → 실패
        resp2 = client.post("/auth/refresh", json={
            "refresh_token": old_refresh,
        })
        assert resp2.status_code == 401

    def test_access_without_token(self):
        """토큰 없이 보호 엔드포인트 → 401/403 (인증 필요)"""
        resp = client.post("/analyze/sync", json={
            "source_code": "print('hello')",
        })
        assert resp.status_code in (401, 403)

    def test_access_with_invalid_token(self):
        """잘못된 토큰 → 401"""
        resp = client.post(
            "/analyze/sync",
            json={"source_code": "print('hello')"},
            headers=_auth_header("invalid.token.here"),
        )
        assert resp.status_code == 401


# ================================================================
# 분석 엔드포인트 테스트
# ================================================================
class TestAnalyze:
    def test_analyze_basic(self):
        """★ 핵심: 코드 분석 → SCI 점수 + 근거 JSON 응답"""
        tokens = _login()
        resp = client.post(
            "/analyze/sync",
            json={"source_code": BAD_CODE},
            headers=_auth_header(tokens["access_token"]),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["sci_score"] > 0
        assert data["grade"] in ("A", "B", "C", "D", "F")
        assert len(data["findings"]) >= 1
        assert len(data["axis_summaries"]) == 3
        assert data["analysis_id"] != ""

    def test_analyze_bad_code_high_score(self):
        """bad 코드 → D 또는 F 등급"""
        tokens = _login()
        resp = client.post(
            "/analyze/sync",
            json={"source_code": BAD_CODE},
            headers=_auth_header(tokens["access_token"]),
        )
        data = resp.json()
        assert data["grade"] in ("D", "F")
        assert data["sci_score"] > 50

    def test_analyze_findings_structure(self):
        """근거(findings) 필드 구조 검증"""
        tokens = _login()
        resp = client.post(
            "/analyze/sync",
            json={"source_code": BAD_CODE},
            headers=_auth_header(tokens["access_token"]),
        )
        data = resp.json()
        for finding in data["findings"]:
            assert "axis" in finding
            assert "severity" in finding
            assert "line" in finding
            assert "function_name" in finding
            assert "problem" in finding
            assert "suggestion" in finding
            assert "estimated_reduction" in finding

    def test_analyze_with_region(self):
        """지역 코드 지정 → 탄소 강도 변경"""
        tokens = _login()
        # 한국 (450)
        kr = client.post(
            "/analyze/sync",
            json={"source_code": BAD_CODE, "region": "KR"},
            headers=_auth_header(tokens["access_token"]),
        ).json()
        # 프랑스 (60)
        fr = client.post(
            "/analyze/sync",
            json={"source_code": BAD_CODE, "region": "FR"},
            headers=_auth_header(tokens["access_token"]),
        ).json()
        assert fr["sci_score"] < kr["sci_score"]

    def test_analyze_cost_fields_present(self):
        """덩어리 2: 비용 노출 필드 (estimated_cost / cost_per_kwh / cost_currency)"""
        tokens = _login()
        resp = client.post(
            "/analyze/sync",
            json={"source_code": BAD_CODE, "region": "KR"},
            headers=_auth_header(tokens["access_token"]),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "estimated_cost" in data
        assert "cost_per_kwh" in data
        assert "cost_currency" in data
        assert data["estimated_cost"] >= 0
        assert data["cost_per_kwh"] > 0
        assert data["cost_currency"] == "USD"

    def test_analyze_syntax_error(self):
        """문법 오류 코드 → 422"""
        tokens = _login()
        resp = client.post(
            "/analyze/sync",
            json={"source_code": "def broken(:\n  pass"},
            headers=_auth_header(tokens["access_token"]),
        )
        assert resp.status_code == 422

    def test_get_analysis_result(self):
        """GET /analyze/{id} → 저장된 결과 조회"""
        tokens = _login()
        # 먼저 분석 실행
        resp = client.post(
            "/analyze/sync",
            json={"source_code": "x = 1"},
            headers=_auth_header(tokens["access_token"]),
        )
        analysis_id = resp.json()["analysis_id"]

        # 결과 조회
        resp2 = client.get(
            f"/analyze/{analysis_id}",
            headers=_auth_header(tokens["access_token"]),
        )
        assert resp2.status_code == 200
        assert resp2.json()["analysis_id"] == analysis_id

    def test_get_analysis_not_found(self):
        """존재하지 않는 분석 ID → 404"""
        tokens = _login()
        resp = client.get(
            "/analyze/nonexistent",
            headers=_auth_header(tokens["access_token"]),
        )
        assert resp.status_code == 404


# ================================================================
# Rate Limiting 테스트
# ================================================================
class TestRateLimit:
    def test_free_user_rate_limit(self):
        """★ free 유저: 6번째 요청 → 429"""
        tokens = _login("user", "greenpulse")
        headers = _auth_header(tokens["access_token"])

        # 5회 성공
        for i in range(5):
            resp = client.post(
                "/analyze/sync",
                json={"source_code": f"x = {i}"},
                headers=headers,
            )
            assert resp.status_code == 200, f"요청 {i+1} 실패"

        # 6번째 → 429 Too Many Requests
        resp = client.post(
            "/analyze/sync",
            json={"source_code": "x = 999"},
            headers=headers,
        )
        assert resp.status_code == 429
        detail = resp.json()["detail"]
        assert detail["limit"] == 5
        assert "upgrade_hint" in detail

    def test_admin_no_rate_limit(self):
        """admin 유저: 제한 없음"""
        tokens = _login("admin", "greenpulse")
        headers = _auth_header(tokens["access_token"])

        # 10회 모두 성공
        for i in range(10):
            resp = client.post(
                "/analyze/sync",
                json={"source_code": f"x = {i}"},
                headers=headers,
            )
            assert resp.status_code == 200


# ================================================================
# 이력 + 사용자 정보 테스트
# ================================================================
class TestHistory:
    def test_history_empty(self):
        """이력 없는 사용자 → 빈 리스트"""
        tokens = _login()
        resp = client.get("/history", headers=_auth_header(tokens["access_token"]))
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_history_after_analysis(self):
        """분석 후 이력에 기록됨"""
        tokens = _login()
        headers = _auth_header(tokens["access_token"])

        # 분석 실행
        client.post("/analyze/sync", json={"source_code": "x = 1"}, headers=headers)

        # 이력 확인
        resp = client.get("/history", headers=headers)
        history = resp.json()
        assert len(history) >= 1
        assert "analysis_id" in history[0]
        assert "sci_score" in history[0]

    def test_me_endpoint(self):
        """GET /me → 사용자 정보"""
        tokens = _login("admin", "greenpulse")
        resp = client.get("/me", headers=_auth_header(tokens["access_token"]))
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "admin"
        assert data["role"] == "admin"
