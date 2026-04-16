"""
에너지 추정 모델 — 3축 분석
=============================
GreenPulse의 E(에너지) 추정 방법

| 분석 축 | 측정 대상     | 추정 방법                              |
|---------|--------------|---------------------------------------|
| Compute | CPU 연산 비용 | Cyclomatic Complexity x TDP x 실행시간 |
| Data    | DB/네트워크   | 쿼리 수 x IO 에너지 계수               |
| Token   | LLM API 호출  | 토큰 수 x 모델별 에너지 계수            |

참조:
- CPU TDP: Intel/AMD 공식 스펙
- IO 에너지: SPECpower 벤치마크 기반
- 토큰 에너지: SCI for AI (Green Software Foundation, 2025)
"""
from dataclasses import dataclass


# ================================================================
# CPU TDP(Thermal Design Power) 프로필
# ================================================================
# 참조: Intel/AMD 공식 TDP 스펙
CPU_TDP_PROFILES = {
    "low": {"tdp_watts": 15, "description": "저전력 (모바일/ARM)"},
    "medium": {"tdp_watts": 65, "description": "일반 (데스크탑/클라우드)"},
    "high": {"tdp_watts": 125, "description": "고성능 (서버/워크스테이션)"},
    "cloud_default": {"tdp_watts": 85, "description": "클라우드 기본 (t3.medium 급)"},
}

# ================================================================
# IO당 에너지 계수 (kWh/operation)
# ================================================================
# 참조: SPECpower 벤치마크 기반 추정
IO_ENERGY_COEFFICIENTS = {
    "db_simple_query": 0.000001,     # 단순 SELECT 1건
    "db_complex_query": 0.000005,    # JOIN/서브쿼리 포함
    "db_write": 0.000003,            # INSERT/UPDATE/DELETE
    "network_request": 0.000008,     # HTTP 요청 1건
    "file_read": 0.0000005,          # 파일 읽기
    "file_write": 0.000001,          # 파일 쓰기
}

# ================================================================
# LLM 토큰당 에너지 계수 (kWh / 1000 tokens)
# ================================================================
# 참조: SCI for AI 스펙 (Green Software Foundation, 2025)
TOKEN_ENERGY_COEFFICIENTS = {
    "claude-sonnet": 0.0005,         # Claude Sonnet 급
    "claude-haiku": 0.0002,          # Claude Haiku 급
    "claude-opus": 0.001,            # Claude Opus 급
    "gpt-4": 0.0008,                 # GPT-4 급
    "gpt-3.5": 0.0003,              # GPT-3.5 급
    "default": 0.0005,               # 기본값 (중간 모델)
}


@dataclass
class EnergyBreakdown:
    """3축 에너지 분석 결과 — 대시보드의 AxisBreakdown 컴포넌트에 표시"""

    compute_energy_kwh: float    # CPU 연산 에너지 (kWh)
    data_energy_kwh: float       # DB/네트워크 IO 에너지 (kWh)
    token_energy_kwh: float      # LLM 토큰 에너지 (kWh)
    total_energy_kwh: float      # 총 에너지 (kWh)

    # 항목별 상세 내역 (근거 생성에 사용)
    compute_details: dict
    data_details: dict
    token_details: dict


# ================================================================
# Compute Energy 추정 — CPU TDP 기반
# ================================================================
def estimate_compute_energy(
    cyclomatic_complexity: int = 1,
    estimated_executions: int = 1,
    cpu_profile: str = "cloud_default",
    execution_time_seconds: float = 0.001,
) -> tuple[float, dict]:
    """
    Compute Energy 추정

    공식: E_compute = (TDP_W / 1000) x 시간(h) x 복잡도계수 x 실행횟수

    복잡도계수 매핑:
        CC 1~5:   0.3배 (단순 함수)
        CC 6~10:  0.6배 (중간 복잡도)
        CC 11~20: 0.8배 (복잡한 로직)
        CC 20+:   1.0배 (매우 복잡)

    Args:
        cyclomatic_complexity: 순환 복잡도 (radon으로 측정)
        estimated_executions: 추정 실행 횟수
        cpu_profile: CPU TDP 프로필 키
        execution_time_seconds: 추정 실행 시간 (초)

    Returns:
        (에너지 kWh, 상세 내역 dict)
    """
    tdp_watts = CPU_TDP_PROFILES.get(
        cpu_profile, CPU_TDP_PROFILES["cloud_default"]
    )["tdp_watts"]

    # 복잡도 → CPU 사용률 계수 변환
    if cyclomatic_complexity <= 5:
        complexity_factor = 0.3
    elif cyclomatic_complexity <= 10:
        complexity_factor = 0.6
    elif cyclomatic_complexity <= 20:
        complexity_factor = 0.8
    else:
        complexity_factor = 1.0

    # E = (TDP_W / 1000) x 시간(h) x 복잡도계수 x 실행횟수
    execution_time_hours = execution_time_seconds / 3600
    energy_kwh = (
        (tdp_watts / 1000)
        * execution_time_hours
        * complexity_factor
        * estimated_executions
    )

    details = {
        "cyclomatic_complexity": cyclomatic_complexity,
        "complexity_factor": complexity_factor,
        "tdp_watts": tdp_watts,
        "cpu_profile": cpu_profile,
        "estimated_executions": estimated_executions,
        "execution_time_seconds": execution_time_seconds,
    }

    return round(energy_kwh, 10), details


# ================================================================
# Data Energy 추정 — IO당 에너지 계수 기반
# ================================================================
def estimate_data_energy(
    simple_queries: int = 0,
    complex_queries: int = 0,
    write_queries: int = 0,
    network_requests: int = 0,
    file_reads: int = 0,
    file_writes: int = 0,
) -> tuple[float, dict]:
    """
    Data Energy 추정

    공식: E_data = SUM(IO_count x IO_energy_coefficient)

    N+1 쿼리 탐지: simple_queries가 높으면 N+1 패턴 의심
    JOIN 사용: complex_queries 1건이 simple_queries N건보다 효율적

    Returns:
        (에너지 kWh, 상세 내역 dict)
    """
    energy = (
        simple_queries * IO_ENERGY_COEFFICIENTS["db_simple_query"]
        + complex_queries * IO_ENERGY_COEFFICIENTS["db_complex_query"]
        + write_queries * IO_ENERGY_COEFFICIENTS["db_write"]
        + network_requests * IO_ENERGY_COEFFICIENTS["network_request"]
        + file_reads * IO_ENERGY_COEFFICIENTS["file_read"]
        + file_writes * IO_ENERGY_COEFFICIENTS["file_write"]
    )

    total_io = (
        simple_queries + complex_queries + write_queries
        + network_requests + file_reads + file_writes
    )

    details = {
        "simple_queries": simple_queries,
        "complex_queries": complex_queries,
        "write_queries": write_queries,
        "network_requests": network_requests,
        "file_reads": file_reads,
        "file_writes": file_writes,
        "total_io_operations": total_io,
    }

    return round(energy, 10), details


# ================================================================
# Token Energy 추정 — SCI for AI 스펙 기반
# ================================================================
def estimate_token_energy(
    total_tokens: int = 0,
    model: str = "default",
    api_calls: int = 0,
) -> tuple[float, dict]:
    """
    Token Energy 추정

    공식: E_token = (total_tokens / 1000) x token_energy_coefficient

    모델별 에너지 차이:
        Haiku (0.0002) < Sonnet (0.0005) < Opus (0.001) < GPT-4 (0.0008)

    Returns:
        (에너지 kWh, 상세 내역 dict)
    """
    coefficient = TOKEN_ENERGY_COEFFICIENTS.get(
        model, TOKEN_ENERGY_COEFFICIENTS["default"]
    )

    energy = (total_tokens / 1000) * coefficient

    details = {
        "total_tokens": total_tokens,
        "model": model,
        "api_calls": api_calls,
        "energy_per_1k_tokens": coefficient,
    }

    return round(energy, 10), details


# ================================================================
# 3축 통합 에너지 추정
# ================================================================
def estimate_total_energy(
    compute_args: dict = None,
    data_args: dict = None,
    token_args: dict = None,
) -> EnergyBreakdown:
    """
    3축 에너지 통합 추정 — 파이프라인 Analyzer 단계에서 호출

    Args:
        compute_args: estimate_compute_energy 인자 dict
        data_args: estimate_data_energy 인자 dict
        token_args: estimate_token_energy 인자 dict

    Returns:
        EnergyBreakdown — 3축 분석 결과 (대시보드 표시용)
    """
    compute_energy, compute_details = estimate_compute_energy(
        **(compute_args or {})
    )
    data_energy, data_details = estimate_data_energy(
        **(data_args or {})
    )
    token_energy, token_details = estimate_token_energy(
        **(token_args or {})
    )

    total = compute_energy + data_energy + token_energy

    return EnergyBreakdown(
        compute_energy_kwh=compute_energy,
        data_energy_kwh=data_energy,
        token_energy_kwh=token_energy,
        total_energy_kwh=round(total, 10),
        compute_details=compute_details,
        data_details=data_details,
        token_details=token_details,
    )
