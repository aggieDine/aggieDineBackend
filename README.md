# AggieDine — Serverless Service Template

A fully serverless AWS template for AggieDine microservices. Use this template when your service has bursty, low-volume traffic and you want to stay within the AWS free tier (~$0-5/mo).

**Stack:** Python 3.11, FastAPI + Mangum, DynamoDB, S3, AWS SAM, EventBridge, Cognito auth

## When to use this vs the Docker template

| | Docker (`templateApplicationService`) | Serverless (`templateServerlessService`) |
|---|---|---|
| Runtime | Uvicorn in Docker | Lambda via Mangum |
| Database | PostgreSQL (SQLAlchemy) | DynamoDB (boto3) |
| Cache | Redis | S3 |
| Migrations | Alembic | N/A (schemaless) |
| IaC | docker-compose.yml | SAM template.yaml |
| Cost at low traffic | ~$30-40/mo | ~$0-5/mo (free tier) |

Choose **serverless** for low-traffic services, scheduled scrapers, or event-driven workloads. Choose **Docker** if you need relational data, complex queries, or sustained high throughput.

## Prerequisites

- Python 3.11+
- [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html)
- AWS credentials configured (`aws configure`)

## Quick start

```bash
# Clone for your service
cp -r templateServerlessService/ myServiceName/
cd myServiceName/

# Set up virtual environment
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your values
```

## Local development

**Option 1: uvicorn (fast iteration, no AWS emulation)**
```bash
uvicorn app.main:app --reload
# http://localhost:8000/docs for Swagger UI
```

**Option 2: SAM local (Lambda emulation)**
```bash
sam build
sam local start-api
# http://localhost:3000/docs for Swagger UI
```

## Running tests

```bash
pytest
```

Tests use [moto](https://github.com/getmoto/moto) to mock DynamoDB and S3 — no AWS credentials needed.

## Deploy to AWS

```bash
sam build
sam deploy              # first deploy: uses samconfig.toml defaults
sam deploy --guided     # interactive deploy (sets region, stack name, etc.)
```

## How to clone for a new service

1. Copy this folder: `cp -r templateServerlessService/ myService/`
2. Update `SERVICE_NAME` in `.env` and `stack_name` in `samconfig.toml`
3. Replace `example` schemas/routers/services with your domain
4. Define additional DynamoDB access patterns in the services layer
5. Deploy: `sam build && sam deploy`

## Environment variables

| Variable | Description | Default |
|---|---|---|
| `SERVICE_NAME` | Service identifier | `template-serverless-service` |
| `ENVIRONMENT` | Deployment environment | `development` |
| `LOG_LEVEL` | Logging level | `info` |
| `AWS_REGION` | AWS region for boto3 | `us-east-1` |
| `AWS_COGNITO_REGION` | Cognito region | `us-east-1` |
| `AWS_COGNITO_USER_POOL_ID` | Cognito User Pool ID | |
| `AWS_COGNITO_APP_CLIENT_ID` | Cognito App Client ID | |
| `DYNAMODB_TABLE_NAME` | DynamoDB table name | `template-serverless-table` |
| `S3_BUCKET_NAME` | S3 bucket name | `template-serverless-bucket` |

## Cost estimate (AWS free tier)

| Service | Free tier | Typical usage |
|---|---|---|
| API Gateway HTTP | $1/1M requests | Well within free tier |
| Lambda | 1M requests/mo free | Well within free tier |
| DynamoDB | 25 GB storage, 25 RCU/WCU | Well within free tier |
| S3 | 5 GB storage | Well within free tier |
| EventBridge | Free | Free |
| **Total** | | **~$0-5/mo** |
