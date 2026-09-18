from fastapi import FastAPI

from app.db.session import lifespan
from app.domains.auth.router import router as auth_router
from app.domains.users.router import router as users_router

app = FastAPI(
    title="NaijaStay API",
    description="Hotel booking and property management API",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(auth_router)
app.include_router(users_router)

@app.get("/")
def read_root():
    return {"Hello": "World"}
