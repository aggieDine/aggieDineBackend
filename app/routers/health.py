from fastapi import APIRouter, Depends

from app.config import settings
from app.dependencies import get_dynamodb_table

router = APIRouter(tags=["health"])


@router.get("/health")
def health(table=Depends(get_dynamodb_table)):
    dynamo_status = "ok"
    try:
        _ = table.table_status
    except Exception:
        dynamo_status = "unavailable"

    return {
        "status": "ok",
        "service": settings.SERVICE_NAME,
        "dynamodb": dynamo_status,
    }
