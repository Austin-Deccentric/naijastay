from fastapi import FastAPI

app = FastAPI(
    title="NaijaStay API",
    description="Hotel booking and property management API",
    version="1.0.0",
)

@app.get("/")
def read_root():
    return {"Hello": "World"}
