from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import example, health
from app.routers import menu

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
app.include_router(menu.router)

'''
**Example requests:**
GET /menu
GET /menu?date=2026-04-03
GET /menu?date=2026-04-03&location=Commons
GET /menu?date=2026-04-03&period=Breakfast
GET /menu?date=2026-04-03&filters=Vegetarian&filters=Avoiding+Gluten
GET /menu?date=2026-04-03&location=Sbisa&period=Dinner&filters=Vegan
'''


@app.get("/")
async def root():
    return {"service": settings.SERVICE_NAME, "version": settings.VERSION}
