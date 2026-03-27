from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Service
    SERVICE_NAME: str = "template-serverless-service"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "info"
    VERSION: str = "0.1.0"

    # AWS
    AWS_REGION: str = "us-east-1"

    # AWS Cognito
    AWS_COGNITO_REGION: str = "us-east-1"
    AWS_COGNITO_USER_POOL_ID: str = ""
    AWS_COGNITO_APP_CLIENT_ID: str = ""

    # DynamoDB
    DYNAMODB_TABLE_NAME: str = "template-serverless-table"

    # S3
    S3_BUCKET_NAME: str = "template-serverless-bucket"

    @property
    def cognito_jwks_url(self) -> str:
        return (
            f"https://cognito-idp.{self.AWS_COGNITO_REGION}.amazonaws.com/"
            f"{self.AWS_COGNITO_USER_POOL_ID}/.well-known/jwks.json"
        )

    @property
    def cognito_issuer(self) -> str:
        return (
            f"https://cognito-idp.{self.AWS_COGNITO_REGION}.amazonaws.com/"
            f"{self.AWS_COGNITO_USER_POOL_ID}"
        )


settings = Settings()
