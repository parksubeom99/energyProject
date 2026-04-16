# GreenPulse — Claude Code 작업 가이드

> 이 문서는 Claude Code가 길을 잃지 않도록 하는 **네비게이션 파일**입니다.
> 매 STEP 시작 시 이 파일을 다시 읽고, 현재 위치를 확인하세요.

---

## 현재 위치 추적 (Claude Code가 업데이트)

```
[x] STEP 0 — 환경 세팅 (완료 시 x 표시)
[x] STEP 1 — SCI 공식 엔진
[x] STEP 2 — 파서 + 분석기
[x] STEP 3 — 점수 산출 + 근거 생성
[x] STEP 4 — FastAPI + JWT + RBAC
[x] STEP 5 — Kafka 비동기 처리
[ ] STEP 6 — Claude API 최적화 (optimizer)
[ ] STEP 7 — React 대시보드
[ ] STEP 8 — GitHub Actions CI/CD
[ ] STEP 9 — K8s Helm + ArgoCD
[ ] STEP 10 — 통합 테스트 + README
```

---

## 핵심 규칙 — 반드시 지켜야 할 것

1. **DESIGN_V2.md가 설계의 유일한 진실(Source of Truth)**이다. 구조가 모호하면 이 파일을 다시 읽어라.
2. **STEP 순서를 절대 건너뛰지 마라.** 각 STEP은 이전 STEP의 산출물에 의존한다.
3. **각 STEP 완료 시 검증 명령어를 반드시 실행하라.** 검증 통과 전 다음 STEP 진입 금지.
4. **ADR/ 폴더에 설계 결정을 기록하라.** "왜 이렇게 했는가"가 포트폴리오의 핵심.
5. **한글 주석을 코드에 반드시 넣어라.** 면접에서 코드를 보여줄 때 한글 주석이 설명을 대체.
6. **SCI 공식: `SCI = ((E × I) + M) / R`** — ISO/IEC 21031:2024. 이 공식이 프로젝트의 심장.

---

## STEP 0 — 프로젝트 초기화

### 할 일
```bash
mkdir -p greenpulse/{backend/{auth,pipeline,sci,events,tests},frontend/src/{store,api,components},infra/{k8s/helm/greenpulse/templates,argocd},ADR,docs,.github/workflows}
```

### 산출물
- 폴더 구조 생성
- `backend/config.py` (환경 변수 + SOURCE 상수)
- `backend/requirements.txt`
- `backend/Dockerfile`
- `infra/docker-compose.yml` (PostgreSQL + Redis + Kafka + Zookeeper)
- DESIGN_V2.md, ADR/ 복사 완료

### 검증
```bash
docker compose config  # YAML 문법 확인
ls -la greenpulse/backend/pipeline/  # 5개 파일 자리 확인
```

---

## STEP 1 — SCI 공식 엔진 (`backend/sci/`)

### 할 일
- `formula.py` — SCI = ((E × I) + M) / R 구현
- `energy_model.py` — CPU TDP 기반 Compute Energy 추정, IO당 Data Energy 계수, 토큰당 Token Energy 계수
- `carbon_intensity.py` — 지역별 탄소 강도 (한국 기본값: 450 gCO₂/kWh)
- `embodied_carbon.py` — 하드웨어 내재 탄소 (클라우드 인스턴스별 기본값)

### 검증
```bash
cd greenpulse && python -m pytest backend/tests/test_sci_formula.py -v
```
테스트 내용:
- E=1.0, I=450, M=10, R=1000 → SCI = 0.46 확인
- E=0 → SCI = M/R 확인
- R=0 → ZeroDivisionError 처리 확인

### 완료 기준
`pytest` 전부 PASS → STEP 2 진입

---

## STEP 2 — 파서 + 분석기 (`backend/pipeline/parser.py`, `analyzer.py`)

### 할 일
- `parser.py` — Python `ast` 모듈로 코드 파싱. 함수, 루프, DB 호출, API 호출, LLM 호출 추출
- `analyzer.py` — 3축 에너지 추정
  - Compute: Cyclomatic Complexity × 실행 빈도 추정 × TDP 계수
  - Data: SQL 쿼리 수 × 조인 복잡도 × IO 에너지 계수
  - Token: LLM API 호출 횟수 × 토큰 수 추정 × 모델별 에너지 계수

### 검증
```bash
# 샘플 Python 파일 분석
python -c "
from backend.pipeline.parser import parse_code
from backend.pipeline.analyzer import analyze
result = analyze(parse_code(open('samples/sample_bad.py').read()))
print(result)
# {'compute_energy': ..., 'data_energy': ..., 'token_energy': ..., 'total_energy': ...}
"
```

### 완료 기준
샘플 코드 3개 (good/bad/mixed) 분석 결과 출력 → STEP 3 진입

---

## STEP 3 — 점수 산출 + 근거 생성 (`backend/pipeline/scorer.py`)

### 할 일
- SCI 점수 산출 (formula.py 호출)
- 등급 매기기 (A: 0-10, B: 10-25, C: 25-50, D: 50-100, F: 100+)
- 항목별 근거 생성 (어떤 라인이 왜 에너지를 많이 쓰는지)
- 개선 제안 텍스트 자동 생성

### 검증
```bash
python -m pytest backend/tests/test_analyzer.py -v
```

### 완료 기준
bad 코드 → D등급 + 근거 3개 이상 출력 → STEP 4 진입

---

## STEP 4 — FastAPI + JWT + RBAC (`backend/main.py`, `backend/auth/`)

### 할 일
- `main.py` — FastAPI 앱, CORS, 엔드포인트 등록
- `auth/jwt_handler.py` — JWT 발급/검증 + Refresh Token Rotation
- `auth/rbac.py` — Role 기반 접근 제어 (free: 일 5회, pro: 무제한)
- 엔드포인트:
  - POST `/auth/token` — 로그인
  - POST `/auth/refresh` — 토큰 갱신
  - POST `/analyze` — 코드 분석 요청 (JWT 필수)
  - GET `/analyze/{id}` — 분석 결과 조회
  - GET `/history` — 분석 이력

### 검증
```bash
# 서버 기동
uvicorn backend.main:app --reload &

# 토큰 발급
curl -X POST localhost:8000/auth/token -d "username=admin&password=greenpulse"

# 분석 요청
curl -X POST localhost:8000/analyze \
  -H "Authorization: Bearer {token}" \
  -F "file=@samples/sample_bad.py"
```

### 완료 기준
curl로 분석 요청 → SCI 점수 + 근거 JSON 응답 → STEP 5 진입

---

## STEP 5 — Kafka 비동기 처리 (`backend/events/`)

### 할 일
- `kafka_producer.py` — 분석 요청 이벤트 발행
- `kafka_consumer.py` — 워커가 이벤트 수신 → 파이프라인 실행
- POST `/analyze` → Kafka 발행 → 202 즉시 응답 → 워커가 백그라운드 처리
- GET `/analyze/{id}` → 결과 폴링 (Redis 캐시)

### 검증
```bash
docker compose up -d kafka zookeeper
python -m pytest backend/tests/test_kafka.py -v
```

### 완료 기준
분석 요청 → Kafka 메시지 확인 → 결과 Redis 저장 확인 → STEP 6 진입

---

## STEP 6 — Claude API 최적화 코드 생성 (`backend/pipeline/optimizer.py`)

### 할 일
- scorer 결과에서 가장 점수 낮은 항목 추출
- Claude API 호출 → 해당 부분 리팩토링 코드 생성
- Before/After SCI 비교 (`verifier.py`)

### 검증
```bash
# 최적화 코드 생성
python -c "
from backend.pipeline.optimizer import optimize
result = optimize('samples/sample_bad.py')
print(result['optimized_code'][:500])
print(f'Before SCI: {result[\"before_sci\"]}, After SCI: {result[\"after_sci\"]}')
"
```

### 완료 기준
Before > After SCI 확인 + 최적화 코드 문법 유효성 → STEP 7 진입

---

## STEP 7 — React 대시보드 (`frontend/`)

### 할 일
- `App.jsx` — 로그인 + 메인 레이아웃
- `ScoreGauge.jsx` — SCI 점수 게이지 (등급별 색상)
- `AxisBreakdown.jsx` — Compute/Data/Token 3축 상세
- `CodeDiff.jsx` — Before/After 코드 비교
- `TrendChart.jsx` — 분석 이력 트렌드 차트
- Zustand store + React Query API 연동

### 검증
```bash
cd frontend && npm run dev
# 브라우저에서 4개 뷰 렌더링 확인
```

### 완료 기준
로그인 → 파일 업로드 → SCI 점수 표시 → 최적화 코드 표시 → STEP 8 진입

---

## STEP 8 — GitHub Actions CI/CD (`.github/workflows/`)

### 할 일
- `ci.yml` — PR 시: pytest → lint → SCI 관문 (assert score < threshold)
- `cd.yml` — main push 시: Docker build → ECR push → ArgoCD 동기화 트리거

### 검증
```bash
# 로컬에서 CI 시뮬레이션
python -m pytest backend/tests/ -v
```

### 완료 기준
YAML 문법 검증 + 로컬 pytest 전체 통과 → STEP 9 진입

---

## STEP 9 — K8s Helm + ArgoCD (`infra/`)

### 할 일
- `k8s/helm/greenpulse/Chart.yaml` — Helm Chart 정의
- `templates/deployment-api.yaml` — API 서버 Deployment
- `templates/deployment-worker.yaml` — 분석 워커 Deployment
- `templates/hpa.yaml` — HPA 오토스케일링 (CPU 70% → 스케일아웃)
- `templates/service.yaml`, `ingress.yaml`
- `values-dev.yaml`, `values-prod.yaml` — 환경 분리
- `argocd/application.yaml` — ArgoCD Application 정의

### 검증
```bash
# Helm 템플릿 렌더링 검증
helm template greenpulse infra/k8s/helm/greenpulse -f infra/k8s/helm/greenpulse/values-dev.yaml
```

### 완료 기준
Helm template 렌더링 성공 + ArgoCD YAML 유효성 → STEP 10 진입

---

## STEP 10 — 통합 테스트 + README

### 할 일
- E2E 테스트: 코드 업로드 → SCI 점수 → 최적화 → Before/After
- 핵심 가설 테스트: `assert pearson_r > 0.7`
- README.md 작성 (스크린샷 포함)
- docs/SCI_METHODOLOGY.md — SCI 방법론 상세 문서
- docs/DEPLOYMENT.md — K8s 배포 가이드

### 검증
```bash
python -m pytest backend/tests/ -v --tb=short
```

### 완료 기준
전체 테스트 PASS + README 완성 → 프로젝트 완료

---

## 비상 탈출 규칙

1. **3번 연속 같은 오류** → 진도 멈추고 "현재 STEP X에서 Y 오류 반복. ROADMAP.md 다시 읽겠습니다" 선언
2. **STEP 순서 건너뛰기 충동** → 금지. 이전 STEP 검증 명령어 통과 확인 후에만 진행
3. **설계 변경 필요** → 코드 수정 전 "ADR-XXX 작성 후 진행" 선언
4. **길을 잃었을 때** → 이 파일의 "현재 위치 추적"을 읽고 체크된 마지막 STEP 다음부터 재개
5. **커밋 규칙 (필수 3종 세트)** → 각 STEP 완료 = 검증 통과 + 커밋 + 체크박스 업데이트
   - 커밋 메시지 형식: `STEP X: <한 줄 요약> (N tests pass)`
   - 체크박스 업데이트와 코드를 같은 커밋에 포함
   - .pytest_cache, .claude/ 등 자동 생성 파일은 .gitignore 확인 후 커밋 금지
