"""
Kafka 비동기 처리 테스트
==========================
STEP 5 검증: 분석 요청 → Kafka 발행 → 워커 처리 → 결과 조회

테스트 항목:
1. 이벤트 스키마 직렬화/역직렬화
2. InMemoryProducer 메시지 발행
3. Consumer 파이프라인 실행
4. POST /analyze → 202 + GET /analyze/{id} → completed 결과
5. Rate Limiting이 비동기에서도 동작
"""
import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient
from main import app
from auth.jwt_handler import clear_blacklist
from auth.rbac import clear_all_usage
from events.schemas import AnalysisRequestEvent, AnalysisResultEvent
from events.kafka_producer import get_producer, InMemoryProducer
from events.kafka_consumer import (
    execute_pipeline, get_result, clear_results,
)


client = TestClient(app)

BAD_CODE = '''
import requests

def summarize(text):
    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        json={"model": "claude-sonnet-4-20250514", "messages": [{"role": "user", "content": text}]},
    )
    return response.json()
'''


from events.kafka_consumer import handle_message

@pytest.fixture(autouse=True)
def cleanup():
    clear_blacklist()
    clear_all_usage()
    clear_results()
    # InMemoryProducer에 Consumer 콜백 등록 (startup 이벤트 대체)
    producer = get_producer()
    if isinstance(producer, InMemoryProducer):
        producer.clear()
        if handle_message not in producer._listeners:
            producer.add_listener(handle_message)
    yield
    clear_blacklist()
    clear_all_usage()
    clear_results()


def _login(username="admin", password="greenpulse") -> dict:
    resp = client.post("/auth/token", json={
        "username": username, "password": password,
    })
    return resp.json()


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ================================================================
# 이벤트 스키마 테스트
# ================================================================
class TestEventSchemas:
    def test_request_event_serialize(self):
        """AnalysisRequestEvent 직렬화/역직렬화"""
        event = AnalysisRequestEvent(
            analysis_id="test123",
            username="admin",
            source_code="x = 1",
            region="KR",
        )
        data = event.to_json()
        restored = AnalysisRequestEvent.from_json(data)
        assert restored.analysis_id == "test123"
        assert restored.username == "admin"
        assert restored.source_code == "x = 1"
        assert restored.region == "KR"

    def test_result_event_serialize(self):
        """AnalysisResultEvent 직렬화/역직렬화"""
        event = AnalysisResultEvent(
            analysis_id="test456",
            status="completed",
            sci_score=42.5,
            grade="C",
        )
        data = event.to_json()
        restored = AnalysisResultEvent.from_json(data)
        assert restored.analysis_id == "test456"
        assert restored.status == "completed"
        assert restored.sci_score == 42.5

    def test_request_event_has_timestamp(self):
        """요청 이벤트에 자동 타임스탬프"""
        event = AnalysisRequestEvent(
            analysis_id="ts1",
            username="admin",
            source_code="x = 1",
        )
        assert event.requested_at.endswith("Z")


# ================================================================
# Producer 테스트
# ================================================================
class TestProducer:
    def test_inmemory_producer_send(self):
        """InMemoryProducer에 메시지 발행"""
        producer = get_producer()
        assert isinstance(producer, InMemoryProducer)

        import asyncio
        asyncio.get_event_loop().run_until_complete(
            producer.send("test.topic", b"hello", "key1")
        )

        msgs = producer.get_messages("test.topic")
        assert len(msgs) == 1
        assert msgs[0]["value"] == b"hello"

    def test_producer_clear(self):
        """메시지 초기화"""
        producer = get_producer()
        import asyncio
        asyncio.get_event_loop().run_until_complete(
            producer.send("t", b"data", "k")
        )
        producer.clear()
        assert len(producer.get_messages()) == 0


# ================================================================
# Consumer 파이프라인 테스트
# ================================================================
class TestConsumerPipeline:
    def test_execute_pipeline_success(self):
        """Consumer 파이프라인: 정상 코드 → completed"""
        event = AnalysisRequestEvent(
            analysis_id="pipe1",
            username="admin",
            source_code="x = 1\ny = 2",
        )
        result = execute_pipeline(event)
        assert result.status == "completed"
        assert result.sci_score > 0
        assert result.grade in ("A", "B", "C", "D", "F")

    def test_execute_pipeline_syntax_error(self):
        """Consumer 파이프라인: 구문 오류 → failed"""
        event = AnalysisRequestEvent(
            analysis_id="pipe2",
            username="admin",
            source_code="def broken(:\n  pass",
        )
        result = execute_pipeline(event)
        assert result.status == "failed"
        assert "파싱 실패" in result.error_message

    def test_execute_pipeline_bad_code(self):
        """Consumer 파이프라인: bad 코드 → 높은 SCI"""
        event = AnalysisRequestEvent(
            analysis_id="pipe3",
            username="admin",
            source_code=BAD_CODE,
        )
        result = execute_pipeline(event)
        assert result.status == "completed"
        assert result.sci_score > 10  # LLM 호출로 높은 점수


# ================================================================
# 비동기 엔드포인트 E2E 테스트
# ================================================================
class TestAsyncAnalyze:
    def test_async_analyze_returns_202(self):
        """★ POST /analyze → 202 Accepted"""
        tokens = _login()
        resp = client.post(
            "/analyze",
            json={"source_code": "x = 1"},
            headers=_auth_header(tokens["access_token"]),
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "accepted"
        assert "analysis_id" in data
        assert "poll_url" in data

    def test_async_analyze_then_poll(self):
        """★ 핵심 E2E: POST /analyze → 202 → GET /analyze/{id} → completed"""
        tokens = _login()
        headers = _auth_header(tokens["access_token"])

        # 1. 비동기 분석 요청 → 202
        resp = client.post(
            "/analyze",
            json={"source_code": BAD_CODE},
            headers=headers,
        )
        assert resp.status_code == 202
        analysis_id = resp.json()["analysis_id"]

        # 2. 결과 폴링 → completed (InMemory 모드에서는 즉시 완료)
        resp2 = client.get(
            f"/analyze/{analysis_id}",
            headers=headers,
        )
        assert resp2.status_code == 200
        result = resp2.json()
        assert result["status"] == "completed"
        assert result["sci_score"] > 0
        assert result["grade"] in ("A", "B", "C", "D", "F")
        assert len(result["findings"]) >= 1

    def test_async_analyze_rate_limit(self):
        """비동기 분석에도 Rate Limiting 적용"""
        tokens = _login("user", "greenpulse")
        headers = _auth_header(tokens["access_token"])

        # 5회 성공
        for i in range(5):
            resp = client.post(
                "/analyze",
                json={"source_code": f"x = {i}"},
                headers=headers,
            )
            assert resp.status_code == 202

        # 6번째 → 429
        resp = client.post(
            "/analyze",
            json={"source_code": "x = 999"},
            headers=headers,
        )
        assert resp.status_code == 429

    def test_sync_endpoint_still_works(self):
        """동기 /analyze/sync 호환성 유지"""
        tokens = _login()
        resp = client.post(
            "/analyze/sync",
            json={"source_code": "x = 1"},
            headers=_auth_header(tokens["access_token"]),
        )
        assert resp.status_code == 200
        assert "sci_score" in resp.json()
