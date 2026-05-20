import uuid
from contextlib import asynccontextmanager
from contextvars import ContextVar

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html
from fastapi.responses import JSONResponse
from starlette.staticfiles import StaticFiles

from app.api.auth import router as auth_router
from app.api.common import ApiError
from app.api.scientific_kb import router as scientific_kb_router
from app.config.settings import settings
from app.features.scientific_kb import bootstrap_persistence
from loguru import logger

# ── Correlation-ID context (минималистичная замена удалённого app.core.correlation) ──
# В одном проекте FastAPI/уvicorn ContextVar читается из task'а текущего запроса,
# что даёт thread-safe correlation-id даже под нагрузкой.
_CORRELATION_ID: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def new_correlation_id() -> str:
    return "cid-" + uuid.uuid4().hex[:12]


def set_correlation_id(value: str | None) -> None:
    _CORRELATION_ID.set(value)


def get_correlation_id() -> str | None:
    return _CORRELATION_ID.get()
try:
    from prometheus_client import Counter, Histogram, generate_latest
except Exception:
    class Counter:
        def __init__(self, *args, **kwargs): ...
        def labels(self, *args, **kwargs): return self
        def inc(self, *args, **kwargs): ...

    class Histogram:
        def __init__(self, *args, **kwargs): ...
        def labels(self, *args, **kwargs): return self

        class _Ctx:
            def __enter__(self): ...
            def __exit__(self, a, b, c): ...

        def time(self): return self._Ctx()

    def generate_latest():
        return b''


tags_metadata = [
    {
        "name": "Auth",
        "description": "JWT-аутентификация: регистрация, вход, refresh, профиль.",
    },
    {
        "name": "Scientific KB",
        "description": "Evidence-based scientific knowledge base: publications, claims, evidence, graph, RAG and feedback.",
    },
    {
        "name": "System",
        "description": "Health checks, metrics and documentation.",
    },
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("startup_scientific_kb")
    try:
        status = bootstrap_persistence()
        logger.info("persistence_bootstrap", extra={"status": status})
    except Exception as exc:
        logger.warning("persistence_bootstrap_failed", extra={"error": str(exc)})
    yield


app = FastAPI(
    title="KnowledgeBaseAI Scientific Reasoning Engine",
    description="Scientific knowledge base demo API used by the current frontend.",
    version="1.0.0",
    openapi_tags=tags_metadata,
    redoc_url=None,
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

REQ_COUNTER = Counter("http_requests_total", "Total HTTP requests", ["method", "path", "status"])
LATENCY = Histogram("http_request_latency_ms", "Request latency ms", ["method", "path"])


@app.middleware("http")
async def correlation_middleware(request, call_next):
    """Прокидывает Correlation-ID / Request-ID для трассировки запросов."""
    cid = request.headers.get("X-Correlation-ID") or new_correlation_id()
    set_correlation_id(cid)
    rid = request.headers.get("X-Request-ID") or ("req-" + __import__("uuid").uuid4().hex[:8])
    request.state.request_id = rid
    resp = await call_next(request)
    resp.headers["X-Correlation-ID"] = cid
    resp.headers["X-Request-ID"] = rid
    return resp


@app.middleware("http")
async def metrics_middleware(request, call_next):
    method = request.method
    path = request.url.path
    with LATENCY.labels(method=method, path=path).time():
        resp = await call_next(request)
    REQ_COUNTER.labels(method=method, path=path, status=str(resp.status_code)).inc()
    return resp


def _code_for_status(status: int) -> str:
    if status == 400:
        return "invalid_parameters"
    if status == 404:
        return "not_found"
    if status == 405:
        return "method_not_allowed"
    if status == 422:
        return "validation_error"
    return "internal_error"


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    ae = ApiError(
        code="internal_error",
        message="Internal server error",
        details={"error": exc.__class__.__name__},
        request_id=getattr(request.state, "request_id", None),
        correlation_id=get_correlation_id(),
    )
    return JSONResponse(status_code=500, content=ae.model_dump())


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    msg = exc.detail if isinstance(exc.detail, str) else "Request failed"
    ae = ApiError(
        code=_code_for_status(exc.status_code),
        message=msg,
        details=None,
        request_id=getattr(request.state, "request_id", None),
        correlation_id=get_correlation_id(),
    )
    return JSONResponse(status_code=exc.status_code, content=ae.model_dump())


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    ae = ApiError(
        code="validation_error",
        message="Validation failed",
        details={"errors": exc.errors()},
        request_id=getattr(request.state, "request_id", None),
        correlation_id=get_correlation_id(),
    )
    return JSONResponse(status_code=422, content=ae.model_dump())


@app.get("/redoc", include_in_schema=False)
async def redoc_html():
    return get_redoc_html(
        openapi_url=app.openapi_url,
        title=app.title + " - ReDoc",
        redoc_js_url="/static/redoc/redoc.standalone.js",
    )


@app.get("/health", tags=["System"])
async def health():
    from app.features.scientific_kb import scientific_kb

    persistence_status: dict[str, bool] = {}
    if getattr(scientific_kb, "persistence", None) is not None:
        try:
            persistence_status = scientific_kb.persistence.status()
        except Exception:
            persistence_status = {}
    return {
        "openrouter": bool(settings.openrouter_api_key.get_secret_value()),
        "neo4j": bool(settings.neo4j_uri),
        "persistence": persistence_status,
        "embedding_provider": getattr(scientific_kb, "_embedding_provider", lambda: "deterministic")()
        if hasattr(scientific_kb, "_embedding_provider")
        else "deterministic",
    }


@app.get("/metrics", tags=["System"])
async def metrics():
    return generate_latest()


origins = [o.strip() for o in (settings.cors_allow_origins or "").split(",") if o.strip()]
if origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


app.include_router(auth_router)
app.include_router(scientific_kb_router)
