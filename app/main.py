from fastapi import FastAPI, HTTPException
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

class Coordinates(BaseModel):
    lat: float
    lon: float

class RecommendationRequest(BaseModel):
    current_location: Coordinates
    center_of_interest: Coordinates
    radius: float
    user_id: str
    restriction: Optional[str] = None

@app.post("/recommend")
def get_recommendations(req: RecommendationRequest):
    try:
        curr_loc = (req.current_location.lat, req.current_location.lon)
        center_loc = (req.center_of_interest.lat, req.center_of_interest.lon)

        rec_engine = recommendation(
            current_location=curr_loc, 
            user_id=req.user_id, 
            restriction=req.restriction
        )

        results = rec_engine.recommend(
            center_of_interest=center_loc, 
            radius=req.radius
        )

        return {"status": "success", "results": results}

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal Server Error")