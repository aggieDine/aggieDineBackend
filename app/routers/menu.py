from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import get_dynamodb_table, get_s3_client
from app.schemas.menu import MenuResponse
from app.services import menu as menu_service

router = APIRouter(prefix="/menu", tags=["menu"])


@router.get("", response_model=MenuResponse)
def get_menu(
    date: str | None = Query(default=None, description="Date in YYYY-MM-DD format, defaults to today"),
    location: str | None = Query(default=None, description="Filter by location name (partial match)"),
    period: str | None = Query(default=None, description="Filter by meal period e.g. Breakfast, Lunch, Dinner"),
    filters: list[str] | None = Query(default=None, description="Filter items by diet/allergen labels e.g. Vegetarian, Vegan, Egg"),
    table=Depends(get_dynamodb_table),
    s3=Depends(get_s3_client),
):
    data = menu_service.get_menu(table, s3, date, location, period, filters)
    if data is None:
        raise HTTPException(status_code=404, detail=f"No menu data found for date: {date}")
    return data