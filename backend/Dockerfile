# GreenPulse API 서버 — Python 3.11-slim
# ISO/IEC 21031:2024 SCI 기반 코드 에너지 분석 플랫폼
#
# 빌드: docker build -t gp-api ./backend
# 실행: docker run -p 8000:8000 gp-api

FROM python:3.11-slim AS base

# 환경 변수 — 바이트코드 캐시 비활성화 + 출력 버퍼링 제거
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 의존성 먼저 설치 — Docker 레이어 캐싱 활용
# requirements.txt가 변경되지 않으면 이 레이어는 캐시됨
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 코드 복사
COPY . .

# 헬스체크 — 컨테이너 상태 확인
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# API 서버 포트
EXPOSE 8000

# FastAPI 실행 (프로덕션: --workers 추가)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
