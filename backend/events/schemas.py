"""
이벤트 스키마 — Kafka 메시지 구조 정의
========================================
분석 요청/결과 이벤트의 직렬화/역직렬화 스키마.

토픽:
- greenpulse.analysis.request  — 분석 요청 이벤트 (Producer → Consumer)
- greenpulse.analysis.result   — 분석 결과 이벤트 (Consumer → 저장소)

면접 포인트:
"Kafka 메시지 스키마를 별도 모듈로 분리하여 Producer/Consumer 간
 계약(Contract)을 명확히 했습니다. 프로덕션에서는 Avro/Protobuf로
 스키마 레지스트리와 연동하여 버전 관리합니다."
"""
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime


@dataclass
class AnalysisRequestEvent:
    """
    분석 요청 이벤트 — POST /analyze → Kafka 발행

    Producer가 직렬화하여 Kafka에 발행하고,
    Consumer가 역직렬화하여 파이프라인을 실행한다.
    """
    analysis_id: str                # 분석 고유 ID (클라이언트 응답용)
    username: str                   # 요청 사용자
    source_code: str                # 분석할 Python 코드
    region: str = "KR"              # 지역 코드 (탄소 강도)
    functional_unit: int = 1        # 기능 단위 (R)
    requested_at: str = ""          # 요청 시간 (ISO 8601)

    def __post_init__(self):
        if not self.requested_at:
            self.requested_at = datetime.utcnow().isoformat() + "Z"

    def to_json(self) -> bytes:
        """Kafka 메시지 직렬화"""
        return json.dumps(asdict(self), ensure_ascii=False).encode("utf-8")

    @classmethod
    def from_json(cls, data: bytes) -> "AnalysisRequestEvent":
        """Kafka 메시지 역직렬화"""
        payload = json.loads(data.decode("utf-8"))
        return cls(**payload)


@dataclass
class AnalysisResultEvent:
    """
    분석 결과 이벤트 — Consumer가 파이프라인 실행 후 생성

    결과 저장소(Redis/PostgreSQL)에 기록되고,
    GET /analyze/{id}로 클라이언트가 폴링한다.
    """
    analysis_id: str                # 분석 고유 ID
    status: str = "pending"         # "pending" | "processing" | "completed" | "failed"
    sci_score: float = 0.0
    grade: str = ""
    grade_label: str = ""
    grade_color: str = ""
    summary_text: str = ""
    axis_summaries: list = field(default_factory=list)
    findings: list = field(default_factory=list)
    total_functions: int = 0
    total_lines: int = 0
    total_energy_kwh: float = 0.0
    total_carbon_gco2: float = 0.0
    error_message: str = ""         # 실패 시 오류 메시지
    completed_at: str = ""          # 완료 시간

    def to_json(self) -> bytes:
        """직렬화"""
        return json.dumps(asdict(self), ensure_ascii=False).encode("utf-8")

    @classmethod
    def from_json(cls, data: bytes) -> "AnalysisResultEvent":
        """역직렬화"""
        payload = json.loads(data.decode("utf-8"))
        return cls(**payload)

    def to_dict(self) -> dict:
        """API 응답용 dict 변환"""
        return asdict(self)
