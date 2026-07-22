from fastapi import FastAPI
from app.routers import services

app = FastAPI(
    title="Platform API",
    description="Internal Developer Platform API for service provisioning",
    version="0.1.0"
)

app.include_router(services.router, prefix="/services", tags=["services"])

@app.get("/health")
def health_check():
    return {"status": "ok"}
