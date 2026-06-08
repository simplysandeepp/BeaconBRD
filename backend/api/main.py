import os
import importlib.util
import time
from datetime import datetime, timezone
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import sys
from dotenv import load_dotenv

# Add the parent directory and nested modules so we can import them
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load env vars once for all routers (e.g., Slack OAuth config).
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INTEGRATION_MODULE_ROOT = os.path.join(PROJECT_ROOT, "Integration Module")
ENABLE_LEGACY_GMAIL_ROUTES = os.getenv("ENABLE_LEGACY_GMAIL_ROUTES", "false").lower() == "true"
CRON_HEALTH_TOKEN = os.getenv("CRON_HEALTH_TOKEN", "").strip()
APP_STARTED_AT = time.time()
load_dotenv(os.path.join(PROJECT_ROOT, "Noise filter module", ".env"), override=False)
load_dotenv(os.path.join(PROJECT_ROOT, ".env"), override=False)

# Legacy integration module path still contains spaces; keep it importable only when explicitly enabled.
if ENABLE_LEGACY_GMAIL_ROUTES and os.path.isdir(INTEGRATION_MODULE_ROOT) and INTEGRATION_MODULE_ROOT not in sys.path:
    sys.path.append(INTEGRATION_MODULE_ROOT)

from .routers import sessions, ingest, review, brd, hitl, slack
from integration_module.routes.gmail_routes import router as gmail_router
from brd_module.storage import init_db


def _load_legacy_gmail_router():
    routes_path = os.path.join(INTEGRATION_MODULE_ROOT, "routes", "gmail_routes.py")
    if not os.path.exists(routes_path):
        return None

    spec = importlib.util.spec_from_file_location("legacy_gmail_routes", routes_path)
    if spec is None or spec.loader is None:
        return None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, "router", None)

# Initialize database (PG or SQLite fallback) on startup
try:
    init_db()
except Exception as e:
    print(f"Warning: Database initialization failed: {e}")

app = FastAPI(
    title="BRD Generation API",
    description="API for the Attributed Knowledge Store and BRD Generation Pipeline",
    version="1.0.0"
)

# ── CORS configuration ──────────────────────────────────────────────────────
# Allowed origins: production frontend + common local-dev ports
ALLOWED_ORIGINS = [
    "https://beacon-brd.vercel.app",
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
    "http://127.0.0.1:5173",
]

# Standard FastAPI CORS middleware — handles preflight & response headers
# correctly for all routes, including error responses.
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=86400,
)

# Additional safety-net middleware: ensures every response (including
# unhandled exceptions and responses from other middleware layers) carries
# CORS headers.  Works alongside CORSMiddleware above — if CORSMiddleware
# already set the headers we don't overwrite them.
@app.middleware("http")
async def cors_header_injector(request: Request, call_next):
    origin = request.headers.get("Origin", "")

    # Determine the allowed origin for this request
    if origin in ALLOWED_ORIGINS:
        allowed_origin = origin
    elif origin and (origin.startswith("http://localhost:") or origin.startswith("http://127.0.0.1:")):
        allowed_origin = origin
    else:
        # For requests with no Origin header (Slack webhooks, curl, Render
        # health-checks, etc.) — still allow through.  CORSMiddleware above
        # handles strict origin enforcement for credentialed requests.
        allowed_origin = origin if origin else "*"

    # Handle preflight OPTIONS requests immediately
    if request.method == "OPTIONS":
        requested_headers = request.headers.get("Access-Control-Request-Headers", "*")
        return JSONResponse(
            status_code=200,
            content={},
            headers={
                "Access-Control-Allow-Origin": allowed_origin,
                "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH",
                "Access-Control-Allow-Headers": requested_headers,
                "Access-Control-Allow-Credentials": "true",
                "Access-Control-Max-Age": "86400",
            },
        )

    try:
        response = await call_next(request)
    except Exception as exc:
        response = JSONResponse(
            status_code=500,
            content={"detail": f"Internal server error: {str(exc)}"},
        )

    # Only set CORS headers if CORSMiddleware didn't already set them
    if "access-control-allow-origin" not in response.headers:
        response.headers["Access-Control-Allow-Origin"] = allowed_origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
    if "access-control-expose-headers" not in response.headers:
        response.headers["Access-Control-Expose-Headers"] = "*"
    return response

# ── Routers ─────────────────────────────────────────────────────────────────
app.include_router(sessions.router)
app.include_router(ingest.router)
app.include_router(review.router)
app.include_router(brd.router)
app.include_router(hitl.router)
app.include_router(slack.router)
app.include_router(gmail_router)

if ENABLE_LEGACY_GMAIL_ROUTES:
    try:
        gmail_router = _load_legacy_gmail_router()
        if gmail_router is not None:
            app.include_router(gmail_router)
    except Exception as e:
        print(f"Warning: Gmail router not loaded: {e}")


def _build_health_payload():
    return {
        "status": "ok",
        "service": "beacon-backend",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "uptime_seconds": int(time.time() - APP_STARTED_AT),
    }


def _is_authorized_cron_request(request: Request) -> bool:
    if not CRON_HEALTH_TOKEN:
        return True

    query_token = request.query_params.get("token", "")
    header_token = request.headers.get("x-cron-token", "")
    return query_token == CRON_HEALTH_TOKEN or header_token == CRON_HEALTH_TOKEN


@app.get("/")
def read_root():
    return {"status": "ok", "message": "BRD Generation API is running."}


@app.get("/healthz")
def healthz(request: Request):
    if not _is_authorized_cron_request(request):
        return JSONResponse(status_code=401, content={"status": "unauthorized"})

    return _build_health_payload()


@app.head("/healthz")
def healthz_head(request: Request):
    if not _is_authorized_cron_request(request):
        return JSONResponse(status_code=401, content={"status": "unauthorized"})

    return JSONResponse(status_code=200, content={})


@app.get("/wake")
def wake():
    """
    Lightweight endpoint to wake the backend from sleep.
    Returns immediately with wake confirmation and estimated ready time.
    """
    wake_time = datetime.now(timezone.utc)
    estimated_ready_time = wake_time.timestamp() + 30  # 30 seconds wake time

    return {
        "status": "waking",
        "wake_timestamp": wake_time.isoformat(),
        "estimated_ready_timestamp": datetime.fromtimestamp(estimated_ready_time, tz=timezone.utc).isoformat(),
        "estimated_ready_seconds": 30,
        "message": "Backend is waking up"
    }
