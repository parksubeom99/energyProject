"""
Kafka Consumer — 분석 워커
========================================
Kafka 토픽에서 분석 요청 이벤트를 수신하고,
파이프라인(Parser → Analyzer → Scorer)을 실행하여 결과를 저장.

프로덕션: aiokafka.AIOKafkaConsumer로 비동기 소비 + K8s HPA 오토스케일링.
개발/테스트: InMemoryConsumer로 Producer의 콜백을 직접 수신.

면접 포인트:
"Consumer를 별도 워커 프로세스로 분리하여 API 서버와 독립적으로
 스케일링합니다. K8s HPA가 CPU 70% 기준으로 워커 Pod를 자동 증설합니다.
 분석 시간이 긴 코드가 들어와도 API 서버는 영향받지 않습니다."
"""
from datetime import datetime
from typing import Optional, Callable

from config import settings
from events.schemas import AnalysisRequestEvent, AnalysisResultEvent
from pipeline.parser import parse_code
from pipeline.analyzer import analyze
from pipeline.scorer import score
from sci.carbon_intensity import get_carbon_intensity


# ================================================================
# 결과 저장소 (프로덕션: Redis + PostgreSQL)
# ================================================================
# 인메모리 저장소 — 결과 상태 추적
# key: analysis_id, value: AnalysisResultEvent.to_dict()
_result_store: dict[str, dict] = {}


def get_result(analysis_id: str) -> Optional[dict]:
    """분석 결과 조회 (GET /analyze/{id}에서 사용)"""
    return _result_store.get(analysis_id)


def set_result(analysis_id: str, result: dict) -> None:
    """분석 결과 저장"""
    _result_store[analysis_id] = result


def clear_results() -> None:
    """결과 저장소 초기화 (테스트용)"""
    _result_store.clear()


# ================================================================
# 분석 파이프라인 실행
# ================================================================
def execute_pipeline(event: AnalysisRequestEvent) -> AnalysisResultEvent:
    """
    분석 파이프라인 실행 — Consumer의 핵심 로직

    흐름: AnalysisRequestEvent → Parser → Analyzer → Scorer → AnalysisResultEvent

    이 함수는 동기적으로 실행되며, Consumer가 Kafka 메시지를 수신할 때마다 호출.
    """
    try:
        # pending → processing 상태 업데이트
        processing_result = AnalysisResultEvent(
            analysis_id=event.analysis_id,
            status="processing",
        )
        set_result(event.analysis_id, processing_result.to_dict())

        # 파이프라인 실행: Parser → Analyzer → Scorer
        carbon_intensity = get_carbon_intensity(event.region)
        parsed = parse_code(event.source_code)

        if parsed.errors:
            # 파싱 실패
            return AnalysisResultEvent(
                analysis_id=event.analysis_id,
                status="failed",
                error_message=f"코드 파싱 실패: {parsed.errors[0]}",
                completed_at=datetime.utcnow().isoformat() + "Z",
            )

        analysis = analyze(
            parsed,
            carbon_intensity=carbon_intensity,
            functional_unit=event.functional_unit,
        )
        report = score(analysis)

        # 성공 결과 생성
        return AnalysisResultEvent(
            analysis_id=event.analysis_id,
            status="completed",
            sci_score=report.sci_score,
            grade=report.grade,
            grade_label=report.grade_label,
            grade_color=report.grade_color,
            summary_text=report.summary_text,
            axis_summaries=[
                {
                    "axis": s.axis,
                    "energy_kwh": s.energy_kwh,
                    "energy_gco2": s.energy_gco2,
                    "percentage": s.percentage,
                    "finding_count": s.finding_count,
                    "status": s.status,
                }
                for s in report.axis_summaries
            ],
            findings=[
                {
                    "axis": f.axis,
                    "severity": f.severity,
                    "line": f.line,
                    "function_name": f.function_name,
                    "problem": f.problem,
                    "energy_impact": f.energy_impact,
                    "suggestion": f.suggestion,
                    "estimated_reduction": f.estimated_reduction,
                }
                for f in report.findings
            ],
            total_functions=report.total_functions,
            total_lines=report.total_lines,
            total_energy_kwh=report.total_energy_kwh,
            total_carbon_gco2=report.total_carbon_gco2,
            completed_at=datetime.utcnow().isoformat() + "Z",
        )

    except Exception as e:
        return AnalysisResultEvent(
            analysis_id=event.analysis_id,
            status="failed",
            error_message=str(e),
            completed_at=datetime.utcnow().isoformat() + "Z",
        )


async def handle_message(topic: str, value: bytes) -> None:
    """
    Kafka 메시지 핸들러 — Producer 콜백 또는 Consumer 루프에서 호출

    1. 메시지 역직렬화
    2. 파이프라인 실행
    3. 결과 저장소에 기록
    """
    if topic != settings.KAFKA_TOPIC_ANALYSIS:
        return

    event = AnalysisRequestEvent.from_json(value)

    # 파이프라인 실행
    result = execute_pipeline(event)

    # 결과 저장 (GET /analyze/{id} 폴링 대상)
    set_result(event.analysis_id, result.to_dict())


# ================================================================
# 워커 메인 — K8s Pod 진입점
# ================================================================
# Helm: command: ["python", "-m", "events.kafka_consumer"]
# 프로덕션: aiokafka.AIOKafkaConsumer로 Kafka 토픽 지속 소비
# 개발: InMemoryProducer 콜백으로 동작하므로 이 블록은 미사용
if __name__ == "__main__":
    import asyncio
    import signal
    import sys

    print("[Worker] GreenPulse 분석 워커 시작")
    print(f"[Worker] Kafka: {settings.KAFKA_BOOTSTRAP_SERVERS}")
    print(f"[Worker] Topic: {settings.KAFKA_TOPIC_ANALYSIS}")
    print(f"[Worker] Group: {settings.KAFKA_GROUP_ID}")

    # 프로덕션 Kafka Consumer 루프
    # aiokafka가 설치된 환경에서만 동작
    async def run_consumer():
        try:
            from aiokafka import AIOKafkaConsumer

            consumer = AIOKafkaConsumer(
                settings.KAFKA_TOPIC_ANALYSIS,
                bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
                group_id=settings.KAFKA_GROUP_ID,
                auto_offset_reset="earliest",
            )
            await consumer.start()
            print("[Worker] Kafka Consumer 연결 완료. 메시지 대기 중...")

            try:
                async for msg in consumer:
                    print(f"[Worker] 메시지 수신: key={msg.key}")
                    await handle_message(msg.topic, msg.value)
            finally:
                await consumer.stop()

        except ImportError:
            print("[Worker] aiokafka 미설치 — 대기 모드 (개발 환경)")
            # 개발 환경: aiokafka 없이 대기
            while True:
                await asyncio.sleep(60)

    # Graceful shutdown
    loop = asyncio.new_event_loop()

    def shutdown(sig, frame):
        print(f"[Worker] {sig} 수신. 종료 중...")
        loop.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    loop.run_until_complete(run_consumer())
