"""
GreenPulse API 서버 — FastAPI 진입점
=====================================
ISO/IEC 21031:2024 SCI 기반 코드 에너지 분석 + AI 자동 최적화 플랫폼

엔드포인트:
- POST /auth/token       로그인 → JWT 발급
- POST /auth/refresh     토큰 갱신 (RTR)
- POST /analyze          비동기 분석 → Kafka 발행 → 202 즉시 응답
- POST /analyze/sync     동기 분석 → 즉시 결과 반환 (호환용)
- GET  /analyze/{id}     분석 결과 조회 (폴링)
- GET  /history          분석 이력
- GET  /health           헬스체크

보안: JWT + RBAC + Rate Limiting
비동기: Kafka Producer → Consumer 워커 → 결과 저장소
"""
import uuid
from datetime import datetime

from fastapi import FastAPI, HTTPException, Depends, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from config import settings
from auth.models import (
    TokenRequest, TokenResponse, RefreshRequest,
    AnalyzeRequest, AnalyzeResponse, HistoryItem,
    UserResponse, Role,
)
from auth.jwt_handler import (
    create_access_token, create_refresh_token,
    verify_token, rotate_refresh_token, clear_blacklist,
)
from auth.rbac import check_rate_limit, increment_usage
from pipeline.parser import parse_code
from pipeline.analyzer import analyze
from pipeline.scorer import score
from sci.carbon_intensity import get_carbon_intensity
from sci.cost import estimate_cost
from events.schemas import AnalysisRequestEvent
from events.kafka_producer import publish_analysis_request, get_producer
from events.kafka_consumer import (
    get_result as get_async_result,
    set_result as set_async_result,
    handle_message,
)


# ================================================================
# FastAPI 앱 생성
# ================================================================
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "ISO/IEC 21031:2024 SCI 기반 코드 에너지 분석 + AI 자동 최적화 플랫폼. "
        "코드를 넣으면 SCI 점수가 나오고, AI가 최적화 코드를 산출합니다."
    ),
    docs_url="/docs",      # Swagger UI
    redoc_url="/redoc",    # ReDoc
)

# CORS 설정 — 프론트엔드(React) 접근 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# JWT Bearer 인증 스키마
security = HTTPBearer()


# ================================================================
# Kafka InMemory Consumer 연결 (개발 환경)
# ================================================================
# InMemoryProducer에 Consumer 콜백 등록 → 발행 즉시 처리
# 프로덕션: 별도 워커 프로세스(kafka_consumer.py)가 독립 실행
@app.on_event("startup")
async def _register_consumer():
    """앱 시작 시 InMemory Consumer 콜백 등록"""
    producer = get_producer()
    if hasattr(producer, "add_listener"):
        producer.add_listener(handle_message)


# ================================================================
# 임시 사용자 저장소 (프로덕션: PostgreSQL)
# ================================================================
# 개발 환경용 하드코딩 사용자. 프로덕션에서는 DB로 교체.
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

DEMO_USERS = {
    "admin": {
        "username": "admin",
        "hashed_password": pwd_context.hash("greenpulse"),
        "role": Role.ADMIN,
        "is_active": True,
    },
    "user": {
        "username": "user",
        "hashed_password": pwd_context.hash("greenpulse"),
        "role": Role.FREE,
        "is_active": True,
    },
    "pro_user": {
        "username": "pro_user",
        "hashed_password": pwd_context.hash("greenpulse"),
        "role": Role.PRO,
        "is_active": True,
    },
}


# ================================================================
# 임시 분석 결과 저장소 (프로덕션: PostgreSQL + Redis 캐시)
# ================================================================
_analysis_store: dict[str, dict] = {}
_user_history: dict[str, list] = {}


# ================================================================
# 의존성 함수 — JWT 토큰에서 사용자 정보 추출
# ================================================================
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """
    Authorization: Bearer {token} 헤더에서 JWT 검증 후 사용자 반환

    Raises:
        HTTPException 401: 토큰 무효/만료
        HTTPException 403: 비활성 사용자
    """
    try:
        payload = verify_token(credentials.credentials, expected_type="access")
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    user = DEMO_USERS.get(payload.sub)
    if not user:
        raise HTTPException(status_code=401, detail="사용자를 찾을 수 없습니다")
    if not user["is_active"]:
        raise HTTPException(status_code=403, detail="비활성 계정입니다")

    return {**user, "username": payload.sub, "role": payload.role}


# ================================================================
# 헬스체크
# ================================================================
@app.get("/health", tags=["시스템"])
async def health_check():
    """서버 상태 확인 — Docker HEALTHCHECK + 모니터링용"""
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }


# ================================================================
# 인증 엔드포인트
# ================================================================
@app.post("/auth/token", response_model=TokenResponse, tags=["인증"])
async def login(request: TokenRequest):
    """
    로그인 → JWT Access + Refresh Token 발급

    데모 계정:
    - admin / greenpulse (관리자, 무제한)
    - user / greenpulse (무료, 일 5회)
    - pro_user / greenpulse (프로, 일 1000회)
    """
    user = DEMO_USERS.get(request.username)
    if not user:
        raise HTTPException(status_code=401, detail="잘못된 사용자명 또는 비밀번호")

    if not pwd_context.verify(request.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="잘못된 사용자명 또는 비밀번호")

    if not user["is_active"]:
        raise HTTPException(status_code=403, detail="비활성 계정입니다")

    role = user["role"]
    access_token = create_access_token(request.username, role)
    refresh_token = create_refresh_token(request.username, role)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.JWT_ACCESS_EXPIRE_MINUTES * 60,
        role=role,
    )


@app.post("/auth/refresh", response_model=TokenResponse, tags=["인증"])
async def refresh_token(request: RefreshRequest):
    """
    Refresh Token Rotation (RTR) — 토큰 갱신

    동작:
    1. 기존 refresh_token 검증 + 블랙리스트 확인
    2. 새 access_token + 새 refresh_token 발급
    3. 기존 refresh_token 블랙리스트 등록 (1회용)
    """
    try:
        new_access, new_refresh = rotate_refresh_token(request.refresh_token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    # 새 토큰에서 role 추출
    payload = verify_token(new_access, expected_type="access")

    return TokenResponse(
        access_token=new_access,
        refresh_token=new_refresh,
        token_type="bearer",
        expires_in=settings.JWT_ACCESS_EXPIRE_MINUTES * 60,
        role=payload.role,
    )


# ================================================================
# 비동기 분석 엔드포인트 (Kafka)
# ================================================================
@app.post("/analyze", tags=["분석"], status_code=202)
async def analyze_async(
    request: AnalyzeRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    비동기 코드 분석 — Kafka 발행 → 202 즉시 응답

    흐름:
    1. Rate Limit 확인
    2. Kafka 토픽에 분석 요청 이벤트 발행
    3. 202 Accepted + analysis_id 즉시 반환
    4. 워커(Consumer)가 백그라운드에서 파이프라인 실행
    5. 클라이언트는 GET /analyze/{id}로 결과 폴링

    K8s HPA 시연: 워커 Pod가 CPU 기준으로 자동 스케일링.
    """
    username = current_user["username"]
    role = current_user["role"]

    # Rate Limit 확인
    allowed, rate_info = check_rate_limit(username, role)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "일일 분석 한도 초과",
                "limit": rate_info["limit"],
                "used": rate_info["used"],
                "reset_at": rate_info["reset_at"],
                "upgrade_hint": "프로 플랜으로 업그레이드하면 일 1000회까지 분석 가능합니다.",
            },
        )

    # 분석 ID 생성
    analysis_id = str(uuid.uuid4())[:8]

    # pending 상태로 결과 저장소에 등록
    from events.schemas import AnalysisResultEvent
    pending = AnalysisResultEvent(analysis_id=analysis_id, status="pending")
    set_async_result(analysis_id, pending.to_dict())

    # Kafka 이벤트 발행
    event = AnalysisRequestEvent(
        analysis_id=analysis_id,
        username=username,
        source_code=request.source_code,
        region=request.region,
        functional_unit=request.functional_unit,
    )
    await publish_analysis_request(event)

    # 사용량 증가
    increment_usage(username)

    # 이력 추가 (pending 상태)
    if username not in _user_history:
        _user_history[username] = []
    _user_history[username].append({
        "analysis_id": analysis_id,
        "sci_score": 0,
        "grade": "",
        "total_lines": 0,
        "analyzed_at": datetime.utcnow().isoformat() + "Z",
    })

    # 202 즉시 응답 — 클라이언트는 GET /analyze/{id}로 폴링
    return {
        "analysis_id": analysis_id,
        "status": "accepted",
        "message": "분석 요청이 접수되었습니다. GET /analyze/{id}로 결과를 확인하세요.",
        "poll_url": f"/analyze/{analysis_id}",
    }


# ================================================================
# 동기 분석 엔드포인트 (호환용)
# ================================================================
@app.post("/analyze/sync", response_model=AnalyzeResponse, tags=["분석"])
async def analyze_sync(
    request: AnalyzeRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    동기 코드 분석 — 즉시 결과 반환 (STEP 4 호환)

    Kafka를 거치지 않고 직접 파이프라인을 실행.
    빠른 테스트, 소규모 코드 분석에 적합.
    """
    username = current_user["username"]
    role = current_user["role"]

    # === Rate Limit 확인 ===
    allowed, rate_info = check_rate_limit(username, role)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "일일 분석 한도 초과",
                "limit": rate_info["limit"],
                "used": rate_info["used"],
                "reset_at": rate_info["reset_at"],
                "upgrade_hint": "프로 플랜으로 업그레이드하면 일 1000회까지 분석 가능합니다.",
            },
        )

    # === 분석 파이프라인 실행 ===
    carbon_intensity = get_carbon_intensity(request.region)

    parsed = parse_code(request.source_code)
    if parsed.errors:
        raise HTTPException(
            status_code=422,
            detail={"error": "코드 파싱 실패", "errors": parsed.errors},
        )

    analysis = analyze(
        parsed,
        carbon_intensity=carbon_intensity,
        functional_unit=request.functional_unit,
    )
    report = score(analysis)

    # === 비용 산출 (덩어리 2 — 1급 지표) ===
    # E (kWh) x P (USD/kWh) = 1회당 비용. region은 요청 인자 그대로 재사용.
    cost_result = estimate_cost(
        energy_kwh=report.total_energy_kwh,
        region=request.region,
    )

    # === 결과 저장 ===
    analysis_id = str(uuid.uuid4())[:8]
    now = datetime.utcnow().isoformat() + "Z"

    response_data = AnalyzeResponse(
        analysis_id=analysis_id,
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
        # === 비용 노출 (덩어리 2) ===
        estimated_cost=cost_result.estimated_cost,
        cost_per_kwh=cost_result.cost_per_kwh,
        cost_currency=cost_result.currency,
        analyzed_at=now,
    )

    # 저장소에 보관
    _analysis_store[analysis_id] = response_data.model_dump()

    # 이력 추가
    if username not in _user_history:
        _user_history[username] = []
    _user_history[username].append({
        "analysis_id": analysis_id,
        "sci_score": report.sci_score,
        "grade": report.grade,
        "total_lines": report.total_lines,
        "analyzed_at": now,
    })

    # 사용량 증가
    increment_usage(username)

    return response_data


@app.get("/analyze/{analysis_id}", tags=["분석"])
async def get_analysis(
    analysis_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    분석 결과 조회 (동기 + 비동기 모두 지원)

    비동기 모드: status가 "pending"/"processing"/"completed"/"failed" 중 하나.
    동기 모드: 항상 완료된 결과 반환.

    클라이언트 폴링 패턴:
      while status != "completed": sleep(1) → GET /analyze/{id}
    """
    # 비동기 결과 저장소 먼저 확인
    result = get_async_result(analysis_id)
    if result:
        return result

    # 동기 결과 저장소 확인 (STEP 4 호환)
    result = _analysis_store.get(analysis_id)
    if result:
        return result

    raise HTTPException(status_code=404, detail="분석 결과를 찾을 수 없습니다")


@app.get("/history", response_model=list[HistoryItem], tags=["분석"])
async def get_history(
    current_user: dict = Depends(get_current_user),
):
    """분석 이력 조회 (현재 사용자)"""
    username = current_user["username"]
    history = _user_history.get(username, [])
    # 최신순 정렬
    return sorted(history, key=lambda x: x["analyzed_at"], reverse=True)


# ================================================================
# 사용자 정보
# ================================================================
@app.get("/me", response_model=UserResponse, tags=["사용자"])
async def get_me(current_user: dict = Depends(get_current_user)):
    """현재 사용자 정보 + Rate Limit 상태"""
    return UserResponse(
        username=current_user["username"],
        role=current_user["role"],
        is_active=current_user["is_active"],
    )
