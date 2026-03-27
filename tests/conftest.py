import os
from collections.abc import AsyncGenerator

import boto3
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from moto import mock_aws

from app.dependencies import get_dynamodb_table
from app.main import app
from app.middleware.auth import get_current_user

os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["AWS_SECURITY_TOKEN"] = "testing"
os.environ["AWS_SESSION_TOKEN"] = "testing"
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
os.environ["DYNAMODB_TABLE_NAME"] = "test-table"
os.environ["S3_BUCKET_NAME"] = "test-bucket"


@pytest_asyncio.fixture(autouse=True)
def aws_mocks():
    with mock_aws():
        # Create mock DynamoDB table
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        dynamodb.create_table(
            TableName="test-table",
            KeySchema=[
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "PK", "AttributeType": "S"},
                {"AttributeName": "SK", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # Create mock S3 bucket
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-bucket")

        def override_get_dynamodb_table():
            return dynamodb.Table("test-table")

        async def override_get_current_user() -> dict:
            return {
                "sub": "test-user-id",
                "email": "test@tamu.edu",
                "groups": ["students"],
            }

        app.dependency_overrides[get_dynamodb_table] = override_get_dynamodb_table
        app.dependency_overrides[get_current_user] = override_get_current_user

        yield

        app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
