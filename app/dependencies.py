import boto3

from app.config import settings
from app.middleware.auth import get_current_user as _get_current_user


def get_dynamodb_table():
    resource = boto3.resource("dynamodb", region_name=settings.AWS_REGION)
    return resource.Table(settings.DYNAMODB_TABLE_NAME)


def get_s3_client():
    return boto3.client("s3", region_name=settings.AWS_REGION)


async def get_current_user(claims=None) -> dict:
    return await _get_current_user(claims)
