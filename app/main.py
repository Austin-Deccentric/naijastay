import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.core.error_handlers import custom_rate_limit_exceeded_handler
from app.core.rate_limit import limiter
from app.db.session import lifespan
from app.domains.auth.router import router as auth_router
from app.domains.users.router import router as users_router

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
    #Generate or catch the ID
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id
    start_time = time.perf_counter()
    
    response = await call_next(request)
    response_time = time.perf_counter() - start_time
    
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time"] = f"{response_time:.4f}s"
    
    return response

app.add_exception_handler(RateLimitExceeded, custom_rate_limit_exceeded_handler) #type: ignore


app.include_router(auth_router)
app.include_router(users_router)

@app.get("/")
def read_root():
    return {"Hello": "World"}
