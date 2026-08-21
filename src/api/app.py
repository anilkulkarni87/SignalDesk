from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import (
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

from src.actions.workflow import ApprovalWorkflowError
from src.observability import (
    EvaluationUpdate,
    ObservationNotFound,
    ObservabilitySummary,
    RunObservation,
    RunObservationList,
)

from .auth import (
    CSRF_HEADER,
    SESSION_COOKIE,
    InvalidSessionError,
    SessionClaims,
    SessionManager,
)
from .config import APIConfig
from .schemas import (
    ActionDecisionRequest,
    ActionPackageView,
    Customer360View,
    CustomerSearchView,
    DraftSupportActionRequest,
    HealthView,
    InvestigationCreateRequest,
    InvestigationView,
    LoginRequest,
    ReadinessView,
    SessionView,
)
from .resilience import (
    IdempotencyConflict,
    IdempotencyInProgress,
    SlidingWindowRateLimiter,
)
from .service import (
    CustomerNotFound,
    InvestigationLimitReached,
    InvestigationTimedOut,
    InvestigationUnavailable,
    SignalDeskService,
)
from .store import InvestigationNotFound


def create_app(
    config: APIConfig,
    *,
    service: SignalDeskService | None = None,
) -> FastAPI:
    owns_service = service is None
    service = service or SignalDeskService(config)
    sessions = SessionManager(
        config.access_code,
        config.session_secret,
        ttl_seconds=config.session_ttl_seconds,
    )
    login_limiter = SlidingWindowRateLimiter(
        config.login_rate_limit,
        config.rate_limit_window_seconds,
    )
    investigation_limiter = SlidingWindowRateLimiter(
        config.investigation_rate_limit,
        config.rate_limit_window_seconds,
    )
    request_logger = logging.getLogger("signaldesk.api.request")

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        if owns_service:
            service.close()

    app = FastAPI(
        title="SignalDesk API",
        version="commit17_v1",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(config.allowed_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type", CSRF_HEADER, "Idempotency-Key"],
        expose_headers=[
            "x-signaldesk-request-id",
            "x-signaldesk-idempotent-replay",
            "x-signaldesk-original-request-id",
            "Retry-After",
        ],
    )

    @app.middleware("http")
    async def attach_request_id(request: Request, call_next):
        request_id = f"REQ-{uuid4().hex[:20]}"
        request.state.request_id = request_id
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception as exc:
            request_logger.error(
                "http_request_failed",
                extra={
                    "event": "http_request_failed",
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": 500,
                    "duration_ms": round(
                        (time.perf_counter() - started) * 1000,
                        3,
                    ),
                    "error_type": exc.__class__.__name__,
                },
            )
            raise
        response.headers["x-signaldesk-request-id"] = request_id
        request_logger.info(
            "http_request",
            extra={
                "event": "http_request",
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round(
                    (time.perf_counter() - started) * 1000,
                    3,
                ),
            },
        )
        return response

    def enforce_rate_limit(decision) -> None:
        if not decision.allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Request rate limit exceeded",
                headers={"Retry-After": str(decision.retry_after_seconds)},
            )

    def claims_from_request(request: Request) -> SessionClaims:
        token = request.cookies.get(SESSION_COOKIE)
        if not token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
        try:
            return sessions.verify(token)
        except InvalidSessionError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(exc),
            ) from exc

    def write_claims(
        request: Request,
        claims: SessionClaims = Depends(claims_from_request),
    ) -> SessionClaims:
        try:
            sessions.verify_csrf(claims, request.headers.get(CSRF_HEADER))
        except InvalidSessionError as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(exc),
            ) from exc
        return claims

    @app.get("/api/v1/health", response_model=HealthView)
    def health() -> HealthView:
        return HealthView()

    @app.get("/api/v1/health/ready", response_model=ReadinessView)
    async def readiness(response: Response) -> ReadinessView:
        checks = await run_in_threadpool(service.readiness)
        ready = all(value == "ready" for value in checks.values())
        if not ready:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadinessView(
            status="ready" if ready else "not_ready",
            checks=checks,
        )

    @app.post("/api/v1/auth/session", response_model=SessionView)
    def login(
        payload: LoginRequest,
        request: Request,
        response: Response,
    ) -> SessionView:
        client_ip = request.client.host if request.client else "unknown"
        enforce_rate_limit(login_limiter.check(client_ip))
        try:
            issued = sessions.authenticate(payload.access_code, payload.reviewer_id)
        except InvalidSessionError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid workspace credentials",
            ) from exc
        response.set_cookie(
            SESSION_COOKIE,
            issued.token,
            max_age=config.session_ttl_seconds,
            httponly=True,
            secure=config.cookie_secure,
            samesite="strict",
            path="/",
        )
        return SessionView(**issued.claims.model_dump())

    @app.get("/api/v1/auth/session", response_model=SessionView)
    def session(claims: SessionClaims = Depends(claims_from_request)) -> SessionView:
        return SessionView(**claims.model_dump())

    @app.delete("/api/v1/auth/session", status_code=status.HTTP_204_NO_CONTENT)
    def logout(
        response: Response,
        _claims: SessionClaims = Depends(write_claims),
    ) -> None:
        response.delete_cookie(SESSION_COOKIE, path="/")

    @app.get("/api/v1/customers", response_model=CustomerSearchView)
    async def search_customers(
        query: str = Query(default="", max_length=100),
        limit: int = Query(default=20, ge=1, le=50),
        _claims: SessionClaims = Depends(claims_from_request),
    ) -> CustomerSearchView:
        return await run_in_threadpool(service.search_customers, query, limit)

    @app.get("/api/v1/customers/{customer_id}", response_model=Customer360View)
    async def customer_360(
        customer_id: str,
        _claims: SessionClaims = Depends(claims_from_request),
    ) -> Customer360View:
        try:
            return await run_in_threadpool(service.customer_360, customer_id)
        except CustomerNotFound as exc:
            raise HTTPException(status_code=404, detail="Customer not found") from exc

    @app.post(
        "/api/v1/investigations",
        response_model=InvestigationView,
        status_code=status.HTTP_201_CREATED,
    )
    async def investigate(
        payload: InvestigationCreateRequest,
        request: Request,
        response: Response,
        idempotency_key: str | None = Header(
            default=None,
            alias="Idempotency-Key",
            min_length=8,
            max_length=128,
            pattern=r"^[A-Za-z0-9._:-]+$",
        ),
        claims: SessionClaims = Depends(write_claims),
    ) -> InvestigationView:
        enforce_rate_limit(investigation_limiter.check(claims.user_id))
        try:
            outcome = await run_in_threadpool(
                service.investigate,
                claims.user_id,
                payload,
                request.state.request_id,
                idempotency_key,
            )
            if outcome.replayed:
                response.status_code = status.HTTP_200_OK
                response.headers["x-signaldesk-idempotent-replay"] = "true"
                response.headers["x-signaldesk-original-request-id"] = (
                    outcome.view.request_id
                )
            return outcome.view
        except InvestigationTimedOut as exc:
            raise HTTPException(status_code=504, detail=str(exc)) from exc
        except InvestigationLimitReached as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except InvestigationUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except (IdempotencyConflict, IdempotencyInProgress) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get(
        "/api/v1/investigations/{investigation_id}",
        response_model=InvestigationView,
    )
    async def get_investigation(
        investigation_id: str,
        claims: SessionClaims = Depends(claims_from_request),
    ) -> InvestigationView:
        try:
            return await run_in_threadpool(
                service.get_investigation,
                claims.user_id,
                investigation_id,
            )
        except InvestigationNotFound as exc:
            raise HTTPException(
                status_code=404, detail="Investigation not found"
            ) from exc

    @app.post(
        "/api/v1/investigations/{investigation_id}/support-action",
        response_model=ActionPackageView,
        status_code=status.HTTP_201_CREATED,
    )
    async def draft_support_action(
        investigation_id: str,
        payload: DraftSupportActionRequest,
        claims: SessionClaims = Depends(write_claims),
    ) -> ActionPackageView:
        try:
            return await run_in_threadpool(
                service.draft_support_action,
                claims.user_id,
                claims.reviewer_id,
                investigation_id,
                payload,
            )
        except InvestigationNotFound as exc:
            raise HTTPException(
                status_code=404, detail="Investigation not found"
            ) from exc

    @app.post(
        "/api/v1/actions/{action_id}/decision",
        response_model=ActionPackageView,
    )
    async def decide_action(
        action_id: str,
        payload: ActionDecisionRequest,
        claims: SessionClaims = Depends(write_claims),
    ) -> ActionPackageView:
        try:
            return await run_in_threadpool(
                service.decide_action,
                claims.user_id,
                claims.reviewer_id,
                action_id,
                payload.decision,
                payload.reason,
            )
        except InvestigationNotFound as exc:
            raise HTTPException(status_code=404, detail="Action not found") from exc
        except ApprovalWorkflowError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc

    @app.get(
        "/api/v1/observability/summary",
        response_model=ObservabilitySummary,
    )
    async def observability_summary(
        claims: SessionClaims = Depends(claims_from_request),
    ) -> ObservabilitySummary:
        return await run_in_threadpool(
            service.observability_summary,
            claims.user_id,
        )

    @app.get(
        "/api/v1/observability/runs",
        response_model=RunObservationList,
    )
    async def observability_runs(
        limit: int = Query(default=100, ge=1, le=200),
        claims: SessionClaims = Depends(claims_from_request),
    ) -> RunObservationList:
        return await run_in_threadpool(
            service.observability_runs,
            claims.user_id,
            limit,
        )

    @app.get(
        "/api/v1/observability/runs/{request_id}",
        response_model=RunObservation,
    )
    async def observability_run(
        request_id: str,
        claims: SessionClaims = Depends(claims_from_request),
    ) -> RunObservation:
        try:
            return await run_in_threadpool(
                service.observability_run,
                claims.user_id,
                request_id,
            )
        except ObservationNotFound as exc:
            raise HTTPException(status_code=404, detail="Run not found") from exc

    @app.post(
        "/api/v1/observability/runs/{request_id}/evaluation",
        response_model=RunObservation,
    )
    async def evaluate_run(
        request_id: str,
        payload: EvaluationUpdate,
        claims: SessionClaims = Depends(write_claims),
    ) -> RunObservation:
        try:
            return await run_in_threadpool(
                service.evaluate_run,
                claims.user_id,
                request_id,
                payload,
            )
        except ObservationNotFound as exc:
            raise HTTPException(status_code=404, detail="Run not found") from exc

    return app
