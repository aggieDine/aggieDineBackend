from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import example, health

app = FastAPI(
    title=settings.SERVICE_NAME,
    version=settings.VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(example.router)


@app.get("/")
async def root():
    return {"service": settings.SERVICE_NAME, "version": settings.VERSION}
