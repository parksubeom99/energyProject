"""
Kafka Producer — 분석 요청 이벤트 발행
========================================
POST /analyze → AnalysisRequestEvent → Kafka 토픽 발행 → 202 즉시 응답

프로덕션: aiokafka.AIOKafkaProducer로 비동기 발행.
개발/테스트: InMemoryProducer로 Kafka 없이 동작 (테스트 가능).

면접 포인트:
"분석 시간이 10초~5분까지 변동하므로 동기 처리 시 타임아웃 위험이 있습니다.
 Kafka로 비동기 처리하여 즉시 202 응답 후 백그라운드에서 분석을 수행합니다.
 실패 시 Kafka의 재시도 메커니즘으로 안정성을 보장합니다."
"""
import json
from typing import Optional, Callable
from datetime import datetime

from config import settings
from events.schemas import AnalysisRequestEvent, AnalysisResultEvent


# ================================================================
# Producer 인터페이스
# ================================================================
class KafkaProducerInterface:
    """Kafka Producer 추상 인터페이스 — 테스트 교체 가능"""

    async def send(self, topic: str, value: bytes, key: str = "") -> None:
        raise NotImplementedError

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass


# ================================================================
# InMemory Producer — 개발/테스트용
# ================================================================
class InMemoryProducer(KafkaProducerInterface):
    """
    Kafka 없이 동작하는 인메모리 Producer.

    발행된 메시지를 내부 리스트에 저장하여 테스트에서 검증 가능.
    Consumer도 이 리스트를 직접 소비하여 동기적으로 처리.
    """

    def __init__(self):
        self.messages: list[dict] = []
        self._listeners: list[Callable] = []

    async def send(self, topic: str, value: bytes, key: str = "") -> None:
        """메시지 발행 → 내부 리스트 저장 + 리스너 콜백"""
        msg = {"topic": topic, "key": key, "value": value}
        self.messages.append(msg)

        # 등록된 리스너(Consumer)에 즉시 전달
        for listener in self._listeners:
            await listener(topic, value)

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    def add_listener(self, callback: Callable) -> None:
        """Consumer 콜백 등록 — InMemory 모드에서 즉시 처리"""
        self._listeners.append(callback)

    def get_messages(self, topic: str = "") -> list[dict]:
        """특정 토픽의 발행된 메시지 조회 (테스트용)"""
        if topic:
            return [m for m in self.messages if m["topic"] == topic]
        return self.messages.copy()

    def clear(self) -> None:
        """메시지 초기화 (테스트용)"""
        self.messages.clear()


# ================================================================
# Producer 싱글턴 인스턴스
# ================================================================
# 개발 환경: InMemoryProducer
# 프로덕션: AIOKafkaProducer (KAFKA_BOOTSTRAP_SERVERS 설정)
_producer: Optional[KafkaProducerInterface] = None


def get_producer() -> KafkaProducerInterface:
    """현재 Producer 인스턴스 반환 (없으면 InMemory 생성)"""
    global _producer
    if _producer is None:
        _producer = InMemoryProducer()
    return _producer


def set_producer(producer: KafkaProducerInterface) -> None:
    """Producer 인스턴스 교체 (테스트/프로덕션 전환용)"""
    global _producer
    _producer = producer


async def publish_analysis_request(event: AnalysisRequestEvent) -> None:
    """
    분석 요청 이벤트를 Kafka 토픽에 발행

    토픽: greenpulse.analysis.request
    키: analysis_id (파티션 라우팅용)
    """
    producer = get_producer()
    await producer.send(
        topic=settings.KAFKA_TOPIC_ANALYSIS,
        value=event.to_json(),
        key=event.analysis_id,
    )
