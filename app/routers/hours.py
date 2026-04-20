from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import get_dynamodb_table, get_s3_client
from app.schemas.hours import HoursResponse
from app.services import hours as hours_service

router = APIRouter(prefix="/hours", tags=["hours"])


@router.get("", response_model=HoursResponse)
def get_hours(
    date: str | None = Query(default=None, description="Date in YYYY-MM-DD format, defaults to today"),
    table=Depends(get_dynamodb_table),
    s3=Depends(get_s3_client),
):
    data = hours_service.get_hours(table, s3, date)
    if data is None:
        raise HTTPException(status_code=404, detail=f"No hours data found for date: {date}")
    return data