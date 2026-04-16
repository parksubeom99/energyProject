# GreenPulse — 소프트웨어 탄소 강도 분석 + AI 자동 최적화 플랫폼

> **"코드를 넣으면 ISO 국제 표준(SCI) 기반 탄소 강도 점수가 나오고, AI가 최적화 코드를 산출한다"**
> 설계 원칙: 국제 표준 기반 → 정량 분석 → AI 최적화 → Before/After 검증 → CI 관문화

---

## 0. 왜 만들었는가 — 존재 이유 (면접 핵심)

### 문제 정의
2024년 기준 ICT 산업은 전 세계 온실가스 배출의 2.1~3.9%를 차지하며,
2040년까지 14%로 증가할 전망이다 (Belkhir & Elmeligi, 2018).
Green Software Foundation은 이 문제에 대응하여 **SCI(Software Carbon Intensity)**
점수 체계를 만들었고, 2024년 **ISO/IEC 21031:2024** 국제 표준으로 제정되었다.

그러나 현재 SCI를 **코드 레벨에서 자동 측정하고 최적화까지 해주는 도구**는 존재하지 않는다.
- CodeCarbon: Python 학습 시 전력만 측정 (최적화 없음)
- Cloud Carbon Footprint: 클라우드 비용 기반 추정 (코드 분석 없음)
- SonarQube: 코드 품질은 보지만 에너지/탄소는 측정 안 함

### GreenPulse의 위치
| 기존 도구 | 하는 것 | 못하는 것 |
|-----------|---------|-----------|
| CodeCarbon | 런타임 전력 측정 | 코드 분석, 최적화 제안 |
| SonarQube | 코드 스멜 탐지 | 에너지/탄소 측정 |
| Cloud Carbon Footprint | 클라우드 비용→탄소 추정 | 코드 레벨 분석 |
| **GreenPulse** | **코드 정적분석 + SCI 점수 + AI 최적화 코드 산출** | — |

### 수익화 가능성
1. **SaaS B2B**: 기업 ESG 보고서에 소프트웨어 탄소 배출 항목 의무화 추세 → SCI 점수 필요
2. **CI/CD 플러그인**: GitHub Actions/Jenkins에 탄소 관문 추가 → 월 구독
3. **컨설팅**: SCI 점수 개선 → 클라우드 비용 절감 (에너지 효율 = 비용 효율)
4. **규제 대응**: EU CSRD(기업지속가능성보고지침) 2025년 시행 → 소프트웨어 탄소 측정 수요 폭증

---

## 1. 핵심 가설

```
가설: "코드 정적 분석으로 추정한 SCI 점수와, 실제 런타임 전력 측정 SCI 점수의
       상관계수(Pearson r)가 0.7 이상이면, 정적 분석만으로 실용적 탄소 추정이 가능하다"

측정: pytest → assert pearson_r > 0.7
실패 시: 동적 프로파일링 병행 모드 투입
```

---

## 2. SCI 공식 — ISO/IEC 21031:2024

```
SCI = ((E × I) + M) / R

E = 에너지 소비량 (kWh) — 코드가 소비하는 전력
I = 탄소 강도 (gCO₂/kWh) — 지역별 전력의 탄소 배출 계수
M = 내재 탄소 (gCO₂) — 하드웨어 제조 시 배출된 탄소의 할당분
R = 기능 단위 — API 호출 1건, 사용자 1명, 트랜잭션 1건 등

단위: gCO₂eq / R (기능 단위당 탄소 그램)
```

### GreenPulse의 E(에너지) 추정 방법 — 3축 분석

| 분석 축 | 측정 대상 | 추정 방법 | 근거 |
|---------|----------|----------|------|
| **Compute Energy** | CPU 연산 비용 | 코드 복잡도(Cyclomatic) × 실행 빈도 × TDP 계수 | CPU TDP(Thermal Design Power) 기반 추정 |
| **Data Energy** | DB/네트워크 IO | 쿼리 복잡도 + 데이터 전송량 추정 | SPECpower 벤치마크 기반 IO당 에너지 계수 |
| **Token Energy** | LLM API 호출 | 토큰 수 × 모델별 에너지 계수 | SCI for AI 스펙 기반 (GSF 2025) |

---

## 3. 아키텍처 — 파이프라인 패턴

```
[사용자]
    │ 코드/ZIP 업로드
    ▼
┌─────────────────────────────────────────────────────────┐
│  API Gateway (FastAPI)                                   │
│  JWT + RBAC + Rate Limiting                             │
└──────┬──────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────┐
│  분석 파이프라인 (Kafka 이벤트 기반 비동기)               │
│                                                          │
│  ① Parser         코드 파싱 → AST 생성                  │
│       ↓                                                  │
│  ② Analyzer       3축 에너지 추정 → SCI 점수 산출        │
│       ↓                                                  │
│  ③ Scorer         종합 점수 + 항목별 근거 생성            │
│       ↓                                                  │
│  ④ Optimizer      Claude API → 최적화 코드 산출          │
│       ↓                                                  │
│  ⑤ Verifier       Before/After SCI 비교 검증             │
│                                                          │
└──────┬──────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────┐  ┌─────────────────┐
│  PostgreSQL      │  │  Redis           │
│  분석 이력 저장   │  │  결과 캐시       │
└─────────────────┘  └─────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────┐
│  React 대시보드                                          │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │
│  │ SCI 점수  │ │ 3축 상세 │ │ 코드 diff│ │ 이력 추적│   │
│  │ 게이지    │ │ 브레이크 │ │ Before/  │ │ 트렌드   │   │
│  │          │ │ 다운     │ │ After    │ │ 차트     │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘   │
└─────────────────────────────────────────────────────────┘
```

---

## 4. 파일 구조

```
greenpulse/
├── DESIGN_V2.md                    # 이 파일 — 설계 결정 기록
├── ADR/                            # Architecture Decision Records
│   ├── 001-why-sci-standard.md     # SCI 표준 채택 근거
│   ├── 002-why-fastapi.md          # FastAPI 선택 근거
│   ├── 003-why-pipeline.md         # 파이프라인 패턴 선택 근거
│   ├── 004-why-k8s.md             # K8s 배포 선택 근거
│   └── 005-why-not-persona.md     # 5인 토의 미채택 근거
│
├── backend/
│   ├── main.py                     # FastAPI 진입점 + JWT + RBAC
│   ├── config.py                   # 환경 설정 (SOURCE 상수 포함)
│   ├── requirements.txt
│   ├── Dockerfile
│   │
│   ├── auth/
│   │   ├── jwt_handler.py          # JWT 발급/검증 + RTR
│   │   ├── rbac.py                 # 역할 기반 접근 제어
│   │   └── models.py               # User, Role Pydantic 모델
│   │
│   ├── pipeline/                   # 핵심 — 5단계 분석 파이프라인
│   │   ├── parser.py               # ① AST 파싱 (Python ast, Java PMD, Kotlin detekt)
│   │   ├── analyzer.py             # ② 3축 에너지 추정 (compute/data/token)
│   │   ├── scorer.py               # ③ SCI 점수 산출 + 항목별 근거
│   │   ├── optimizer.py            # ④ Claude API → 최적화 코드 생성
│   │   └── verifier.py             # ⑤ Before/After SCI 비교
│   │
│   ├── sci/                        # SCI 계산 엔진
│   │   ├── formula.py              # SCI = ((E × I) + M) / R 구현
│   │   ├── energy_model.py         # 에너지 추정 모델 (TDP, SPECpower 계수)
│   │   ├── carbon_intensity.py     # 지역별 탄소 강도 데이터 (Electricity Maps API)
│   │   └── embodied_carbon.py      # 하드웨어 내재 탄소 추정
│   │
│   ├── events/
│   │   ├── kafka_producer.py       # 분석 요청 이벤트 발행
│   │   ├── kafka_consumer.py       # 분석 결과 수신
│   │   └── schemas.py              # 이벤트 스키마 (Avro/JSON Schema)
│   │
│   └── tests/
│       ├── test_sci_formula.py     # SCI 공식 단위 테스트
│       ├── test_analyzer.py        # 3축 분석 테스트
│       ├── test_pipeline_e2e.py    # 전체 파이프라인 E2E
│       └── test_correlation.py     # 핵심 가설: assert pearson_r > 0.7
│
├── frontend/
│   ├── package.json
│   ├── vite.config.js
│   ├── Dockerfile
│   └── src/
│       ├── App.jsx
│       ├── store/                  # Zustand 상태 관리
│       │   └── analysisStore.js
│       ├── api/
│       │   └── client.js           # JWT 인증 + API 호출
│       └── components/
│           ├── ScoreGauge.jsx      # SCI 점수 게이지 차트
│           ├── AxisBreakdown.jsx   # 3축 상세 분석 뷰
│           ├── CodeDiff.jsx        # Before/After 코드 비교
│           └── TrendChart.jsx      # 분석 이력 트렌드
│
├── infra/
│   ├── docker-compose.yml          # 로컬 개발용
│   ├── docker-compose.prod.yml     # 프로덕션용
│   │
│   ├── k8s/                        # ★ K8s 배포 — 포폴 핵심
│   │   ├── namespace.yaml
│   │   └── helm/
│   │       └── greenpulse/
│   │           ├── Chart.yaml
│   │           ├── values.yaml          # 공통 설정
│   │           ├── values-dev.yaml      # 개발 환경
│   │           ├── values-prod.yaml     # 프로덕션 환경
│   │           └── templates/
│   │               ├── deployment-api.yaml
│   │               ├── deployment-worker.yaml
│   │               ├── deployment-frontend.yaml
│   │               ├── service.yaml
│   │               ├── ingress.yaml
│   │               ├── hpa.yaml          # HPA 오토스케일링
│   │               └── configmap.yaml
│   │
│   └── argocd/                     # ★ ArgoCD GitOps
│       └── application.yaml
│
├── .github/
│   └── workflows/
│       ├── ci.yml                  # PR → pytest → lint → SCI 점수 관문
│       └── cd.yml                  # main → Docker build → ECR → ArgoCD 동기화
│
└── docs/
    ├── API.md                      # OpenAPI 기반 API 문서
    ├── SCI_METHODOLOGY.md          # SCI 점수 산출 방법론 상세
    └── DEPLOYMENT.md               # K8s 배포 가이드
```

---

## 5. 기술 스택 선정 + 근거

| 레이어 | 기술 | 선정 근거 |
|--------|------|----------|
| L1 프론트 | React + Vite + Tailwind | 코드 diff 뷰, 게이지 차트 등 인터랙티브 대시보드에 최적. Vite는 빌드 속도 |
| L2 상태 | Zustand + React Query | Zustand=클라이언트 상태(분석 설정), React Query=서버 데이터(분석 결과 캐싱) |
| L3 API | FastAPI + OpenAPI | Python 생태계(ast, scikit-learn) 활용 + 자동 Swagger 문서. 병원(Spring), 주식(WebFlux)과 차별화 |
| L4 보안 | JWT + RBAC + RTR + Rate Limiting | RBAC으로 무료/프로 유저 분리. RTR로 토큰 보안. Rate Limit으로 API 남용 방지 |
| L5 도메인 | 파이프라인 아키텍처 | DDD/Hexagonal은 병원에서 증명. 에너지는 **데이터 변환 파이프라인** → 다른 아키텍처 경험 |
| L6 데이터 | PostgreSQL + Redis | PG=JSON 처리 강점(분석 결과 저장), Redis=분석 결과 캐시 + 토큰 블랙리스트 |
| L7 메시징 | Kafka | 분석 요청→결과 비동기. 3프로젝트 공통 Kafka → "이벤트 드리븐이 내 설계 원칙" |
| L8 배포 | **K8s(EKS) + Helm + ArgoCD + GH Actions** | ★ 포폴 최대 약점(인프라 C+) 해소. 유일한 K8s 실구현 프로젝트 |
| L9 관측성 | Prometheus + Grafana | 병원=Tempo(트레이싱), 에너지=Prometheus(메트릭) → 관측성 양쪽 커버 |
| L10 테스트 | pytest + assert 관문 | `assert pearson_r > 0.7` = 모델 정확도가 CI 관문. 에너지=pytest, 병원=JUnit, 주식=MockK |

---

## 6. 검증 가능한 결과물 — "실제로 이렇게 사용한다"

### 시나리오 1: 개발자가 Python 파일 업로드
```
입력: user_service.py (N+1 쿼리, 중첩 루프, 불필요한 API 호출 포함)

출력:
┌─────────────────────────────────────┐
│  GreenPulse SCI Score: 34.7         │
│  등급: D (개선 필요)                  │
│                                      │
│  [Compute] 18.2 gCO₂ — 중첩 루프    │
│    → 원인: line 45 O(n²) 루프       │
│    → 제안: dict 조회로 O(n) 변환     │
│                                      │
│  [Data]    12.1 gCO₂ — N+1 쿼리     │
│    → 원인: line 78 반복 SELECT       │
│    → 제안: JOIN으로 1회 쿼리 변환     │
│                                      │
│  [Token]   4.4 gCO₂ — LLM 호출      │
│    → 원인: line 92 매 요청마다 호출   │
│    → 제안: 결과 캐싱 (TTL 1h)        │
│                                      │
│  [최적화 코드 생성]                   │
│  → Claude API가 3개 개선점 적용한     │
│    user_service_optimized.py 산출     │
│                                      │
│  [After 점수] SCI: 12.3 (64% 감소)   │
└─────────────────────────────────────┘
```

### 시나리오 2: CI/CD 관문으로 사용
```yaml
# .github/workflows/ci.yml
- name: GreenPulse SCI 관문
  run: |
    greenpulse analyze ./src --format json > sci_report.json
    python -c "
      import json
      r = json.load(open('sci_report.json'))
      assert r['sci_score'] < 50, f'SCI {r[\"sci_score\"]} > 50 — 코드 최적화 필요'
    "
```

### 시나리오 3: ESG 보고서용 리포트
```
기업 A의 백엔드 서비스 12개 분석 결과:
- 총 SCI: 2,847 gCO₂eq/1000 API호출
- 최악 서비스: payment-service (SCI 890) — N+1 쿼리 47건
- 최적 서비스: auth-service (SCI 23)
- 개선 적용 시 예상 절감: 연간 14.2톤 CO₂eq (약 $8,400 클라우드 비용 절감)
```

---

## 7. 면접 답변 설계

| 면접 질문 | 답변 |
|-----------|------|
| "왜 만들었냐?" | "소프트웨어 탄소 배출이 ISO 표준(21031:2024)이 됐지만, 코드 레벨 자동 측정+최적화 도구가 없어서. SonarQube가 코드 품질을 자동화했듯, SCI 점수를 자동화하는 도구" |
| "SCI 점수가 정확하냐?" | "정적 분석 추정치와 런타임 실측치의 Pearson r > 0.7 검증. pytest로 CI에서 자동 검증. 실패하면 동적 프로파일링 병행" |
| "실제로 쓸 수 있냐?" | "CI 관문으로 통합 가능. ESG 보고서에 소프트웨어 탄소 항목으로 바로 사용. EU CSRD 대응" |
| "왜 K8s?" | "분석 워커가 코드 복잡도에 따라 CPU 부하가 변동. HPA로 자동 스케일링 필수. ArgoCD로 GitOps 배포" |
| "왜 Kafka?" | "분석 요청이 10초~5분까지 변동. 동기 처리 시 타임아웃. Kafka로 비동기 처리 + 재시도 보장" |
| "수익화는?" | "B2B SaaS + CI 플러그인 + ESG 컨설팅. 2025 EU CSRD 시행으로 시장 수요 확인됨" |

---

## 8. 구현 순서 (Claude Code 작업 순서)

| STEP | 산출물 | 검증 방법 | 의존성 |
|------|--------|----------|--------|
| 1 | 폴더 구조 + docker-compose.yml + config.py | `docker compose config` | 없음 |
| 2 | SCI 공식 엔진 (sci/) + 단위 테스트 | `pytest test_sci_formula.py` | STEP 1 |
| 3 | 파서 + 분석기 (pipeline/parser, analyzer) | 샘플 코드 분석 → 점수 출력 | STEP 2 |
| 4 | 점수 산출기 + 근거 생성 (scorer) | 3축 점수 + 근거 텍스트 검증 | STEP 3 |
| 5 | FastAPI + JWT + RBAC + 엔드포인트 | `curl` 테스트 | STEP 4 |
| 6 | Kafka 이벤트 비동기 처리 | 분석 요청→결과 수신 검증 | STEP 5 |
| 7 | Claude API 최적화 코드 생성 (optimizer) | Before/After SCI 비교 | STEP 6 |
| 8 | React 대시보드 | 브라우저 4개 뷰 렌더링 | STEP 7 |
| 9 | GitHub Actions CI/CD | pytest + SCI 관문 + Docker build | STEP 8 |
| 10 | K8s Helm + ArgoCD 배포 | EKS 클러스터 기동 검증 | STEP 9 |

---

*v2.0 | 2026-04-15 | GreenPulse 설계 확정*
*기반: ISO/IEC 21031:2024 (SCI), Green Software Foundation SCI for AI*
