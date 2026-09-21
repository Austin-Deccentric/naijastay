import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.core.error_handlers import custom_rate_limit_exceeded_handler
from app.core.rate_limit import limiter
from app.core.utils import lifespan
from app.domains.auth.router import router as auth_router
from app.domains.bookings.router import root_router as holds_router
from app.domains.bookings.router import router as bookings_router
from app.domains.rooms.router import router as room_types_router
from app.domains.rooms.router import router as rooms_router
from app.domains.users.router import router as users_router

logger = logging.getLogger("naijastay")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    logger.addHandler(handler)
logger.propagate = False

app = FastAPI(
    title="NaijaStay API",
    description="Hotel booking and property management API",
    version="1.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    # allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SlowAPIMiddleware)


@app.middleware("http")
async def add_request_id_and_timing(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id
    start_time = time.perf_counter()

    try:
        response = await call_next(request)
    except Exception:
        elapsed = time.perf_counter() - start_time
        logger.exception("request failed method=%s path=%s request_id=%s duration=%.4fs", request.method, request.url.path, request_id, elapsed)
        raise

    elapsed = time.perf_counter() - start_time
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time"] = f"{elapsed:.4f}s"

    logger.info(
        "request completed method=%s path=%s status=%s request_id=%s duration=%.4fs",
        request.method,
        request.url.path,
        response.status_code,
        request_id,
        elapsed,
    )
    return response


app.add_exception_handler(RateLimitExceeded, custom_rate_limit_exceeded_handler)  # type: ignore


app.include_router(auth_router)
app.include_router(users_router)
app.include_router(rooms_router)
app.include_router(bookings_router)
app.include_router(holds_router)
app.include_router(room_types_router)


@app.get("/")
def read_root():
    return {"Hello": "World"}
