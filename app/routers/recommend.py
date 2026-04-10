from fastapi import APIRouter, HTTPException

from app.schemas.recommend import RecommendationRequest, RecommendationResponse
from app.services.recommend import recommendation

router = APIRouter(prefix="/recommend", tags=["recommend"])


@router.post("/", response_model=RecommendationResponse)
def get_recommendations(req: RecommendationRequest):
    try:
        curr_loc = (req.current_location.lat, req.current_location.lon)
        center_loc = (req.center_of_interest.lat, req.center_of_interest.lon)

        rec_engine = recommendation(
            current_location=curr_loc,
            user_id=req.user_id,
            restriction=req.restriction,
            time=req.time
        )

        results = rec_engine.recommend(
            center_of_interest=center_loc,
            radius=req.radius,
        )

        return {"status": "success", "results": results}

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal Server Error")
