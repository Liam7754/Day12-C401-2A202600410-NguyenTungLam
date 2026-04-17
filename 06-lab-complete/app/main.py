"""
Production AI Agent — Kết hợp tất cả Day 12 concepts

Checklist:
  ✅ Config từ environment (12-factor)
  ✅ Structured JSON logging
  ✅ API Key authentication
  ✅ Rate limiting (10 req/min per user, Redis sliding window)
  ✅ Cost guard ($10/month per user, stored in Redis)
  ✅ Conversation history (stored in Redis — stateless design)
  ✅ Input validation (Pydantic)
  ✅ Health check + Readiness probe
  ✅ Graceful shutdown (SIGTERM)
  ✅ Security headers
  ✅ CORS
  ✅ Error handling
"""
import time
import signal
import logging
import json
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import Optional

import redis as redis_lib
from fastapi import FastAPI, HTTPException, Security, Depends, Request, Response
from fastapi.security.api_key import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

from app.config import settings
from utils.mock_llm import ask as llm_ask

# ─────────────────────────────────────────────────────────
# Logging — JSON structured
# ─────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format='{"ts":"%(asctime)s","lvl":"%(levelname)s","msg":"%(message)s"}',
)
logger = logging.getLogger(__name__)

START_TIME = time.time()
_is_ready = False
_request_count = 0
_error_count = 0

# ─────────────────────────────────────────────────────────
# Redis client (lazy connection — checked in /ready)
# ─────────────────────────────────────────────────────────
_redis: Optional[redis_lib.Redis] = None


def get_redis() -> redis_lib.Redis:
    global _redis
    if _redis is None:
        _redis = redis_lib.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=3,
        )
    return _redis


def redis_ping() -> bool:
    try:
        return get_redis().ping()
    except Exception:
        return False


# ─────────────────────────────────────────────────────────
# Rate Limiter — sliding window in Redis (stateless across instances)
# ─────────────────────────────────────────────────────────
def check_rate_limit(user_key: str):
    r = get_redis()
    now = time.time()
    window_key = f"rate:{user_key}"
    pipe = r.pipeline()
    pipe.zremrangebyscore(window_key, 0, now - 60)
    pipe.zcard(window_key)
    pipe.zadd(window_key, {str(now): now})
    pipe.expire(window_key, 60)
    _, count, *_ = pipe.execute()
    if count >= settings.rate_limit_per_minute:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: {settings.rate_limit_per_minute} req/min",
            headers={"Retry-After": "60"},
        )


# ─────────────────────────────────────────────────────────
# Cost Guard — monthly budget per user in Redis
# ─────────────────────────────────────────────────────────
def _cost_key(user_key: str) -> str:
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    return f"cost:{user_key}:{month}"


def check_and_record_cost(user_key: str, input_tokens: int, output_tokens: int):
    r = get_redis()
    key = _cost_key(user_key)
    cost = (input_tokens / 1000) * 0.00015 + (output_tokens / 1000) * 0.0006
    current = float(r.get(key) or 0)
    if current >= settings.monthly_budget_usd:
        raise HTTPException(
            status_code=402,
            detail=f"Monthly budget of ${settings.monthly_budget_usd} exceeded. Try next month.",
        )
    pipe = r.pipeline()
    pipe.incrbyfloat(key, cost)
    pipe.expireat(key, _next_month_ts())
    pipe.execute()


def _next_month_ts() -> int:
    from calendar import monthrange
    now = datetime.now(timezone.utc)
    days_in_month = monthrange(now.year, now.month)[1]
    remaining = days_in_month - now.day + 1
    return int(time.time()) + remaining * 86400


# ─────────────────────────────────────────────────────────
# Conversation History — stored in Redis (stateless design)
# ─────────────────────────────────────────────────────────
def get_history(session_id: str) -> list[dict]:
    r = get_redis()
    raw = r.get(f"history:{session_id}")
    if not raw:
        return []
    return json.loads(raw)


def save_history(session_id: str, history: list[dict]):
    r = get_redis()
    trimmed = history[-settings.max_history_messages:]
    r.setex(f"history:{session_id}", settings.history_ttl_seconds, json.dumps(trimmed))


# ─────────────────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────────────────
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    if not api_key or api_key != settings.agent_api_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key. Include header: X-API-Key: <key>",
        )
    return api_key


# ─────────────────────────────────────────────────────────
# Lifespan
# ─────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _is_ready
    logger.info(json.dumps({
        "event": "startup",
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
    }))
    # Verify Redis connection on startup
    if redis_ping():
        logger.info(json.dumps({"event": "redis_connected", "url": settings.redis_url}))
    else:
        logger.warning(json.dumps({"event": "redis_unavailable", "url": settings.redis_url}))
    _is_ready = True
    logger.info(json.dumps({"event": "ready"}))

    yield

    _is_ready = False
    logger.info(json.dumps({"event": "shutdown"}))


# ─────────────────────────────────────────────────────────
# App
# ─────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)


@app.middleware("http")
async def request_middleware(request: Request, call_next):
    global _request_count, _error_count
    start = time.time()
    _request_count += 1
    try:
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        # response.headers.pop("server", None)
        if "server" in response.headers:
            del response.headers["server"]
        duration = round((time.time() - start) * 1000, 1)
        logger.info(json.dumps({
            "event": "request",
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "ms": duration,
        }))
        return response
    except Exception:
        _error_count += 1
        raise


# ─────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────
class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000,
                          description="Your question for the agent")
    session_id: str = Field(default="default", max_length=64,
                            description="Session ID for conversation history")


class AskResponse(BaseModel):
    question: str
    answer: str
    model: str
    session_id: str
    history_length: int
    timestamp: str


# ─────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────

@app.get("/", tags=["Info"])
def root():
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "endpoints": {
            "ask": "POST /ask (requires X-API-Key)",
            "health": "GET /health",
            "ready": "GET /ready",
        },
    }


@app.post("/ask", response_model=AskResponse, tags=["Agent"])
async def ask_agent(
    body: AskRequest,
    request: Request,
    _key: str = Depends(verify_api_key),
):
    """
    Send a question to the AI agent.

    **Authentication:** Include header `X-API-Key: <your-key>`

    **Conversation history** is persisted in Redis per session_id.
    """
    user_key = _key[:16]

    # Rate limit per user (Redis sliding window)
    check_rate_limit(user_key)

    # Budget check — estimate input tokens before calling LLM
    input_tokens = len(body.question.split()) * 2
    check_and_record_cost(user_key, input_tokens, 0)

    logger.info(json.dumps({
        "event": "agent_call",
        "session": body.session_id,
        "q_len": len(body.question),
        "client": str(request.client.host) if request.client else "unknown",
    }))

    # Load conversation history from Redis
    history = get_history(body.session_id)
    history.append({"role": "user", "content": body.question})

    # Call LLM (mock or real)
    answer = llm_ask(body.question)

    # Save updated history back to Redis
    history.append({"role": "assistant", "content": answer})
    save_history(body.session_id, history)

    # Record output token cost
    output_tokens = len(answer.split()) * 2
    check_and_record_cost(user_key, 0, output_tokens)

    return AskResponse(
        question=body.question,
        answer=answer,
        model=settings.llm_model,
        session_id=body.session_id,
        history_length=len(history),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.get("/health", tags=["Operations"])
def health():
    """Liveness probe — platform restarts container if this fails."""
    checks = {
        "llm": "mock" if not settings.openai_api_key else "openai",
        "redis": "ok" if redis_ping() else "unavailable",
    }
    return {
        "status": "ok",
        "version": settings.app_version,
        "environment": settings.environment,
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "total_requests": _request_count,
        "checks": checks,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/ready", tags=["Operations"])
def ready():
    """Readiness probe — load balancer stops routing here if not ready."""
    if not _is_ready:
        raise HTTPException(503, "Not ready yet")
    if not redis_ping():
        raise HTTPException(503, "Redis unavailable")
    return {"ready": True}


@app.get("/metrics", tags=["Operations"])
def metrics(_key: str = Depends(verify_api_key)):
    """Basic metrics (protected)."""
    user_key = _key[:16]
    r = get_redis()
    monthly_cost = float(r.get(_cost_key(user_key)) or 0)
    return {
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "total_requests": _request_count,
        "error_count": _error_count,
        "monthly_cost_usd": round(monthly_cost, 4),
        "monthly_budget_usd": settings.monthly_budget_usd,
        "budget_used_pct": round(monthly_cost / settings.monthly_budget_usd * 100, 1),
    }


# ─────────────────────────────────────────────────────────
# Graceful Shutdown — handle SIGTERM from container runtime
# ─────────────────────────────────────────────────────────
def _handle_signal(signum, _frame):
    logger.info(json.dumps({"event": "signal", "signum": signum}))


signal.signal(signal.SIGTERM, _handle_signal)


if __name__ == "__main__":
    logger.info(f"Starting {settings.app_name} on {settings.host}:{settings.port}")
    logger.info(f"API Key: {settings.agent_api_key[:4]}****")
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        timeout_graceful_shutdown=30,
    )
