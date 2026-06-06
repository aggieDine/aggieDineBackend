from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from app.dependencies import get_dynamodb_table
from app.middleware.auth import get_current_user
from app.fcm import register_device_token, unregister_device_token

router = APIRouter(prefix="/userfcm", tags=["user"])


class DeviceTokenRequest(BaseModel):
    device_token: str


@router.post("/register-device", status_code=status.HTTP_204_NO_CONTENT)
def register_device(
    data:  DeviceTokenRequest,
    table=Depends(get_dynamodb_table),
    user:  dict = Depends(get_current_user),
):
    register_device_token(table, user["sub"], data.device_token)


@router.post("/unregister-device", status_code=status.HTTP_204_NO_CONTENT)
def unregister_device(
    data:  DeviceTokenRequest,
    table=Depends(get_dynamodb_table),
    user:  dict = Depends(get_current_user),
):
    unregister_device_token(table, user["sub"], data.device_token)