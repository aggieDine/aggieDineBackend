# Deploying & Testing

## Prerequisites

- [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) installed and configured (`aws configure`)
- [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html) installed

## Build

```bash
sam build
```

## Deploy

First time (guided):

```bash
sam deploy --guided
```

Subsequent deploys (uses saved `samconfig.toml`):

```bash
sam deploy
```

## Test

### Locally

```bash
# Run the API locally
sam local start-api

# Invoke the scraper Lambda once (simulates an EventBridge trigger)
sam local invoke ScraperFunction

# Invoke with a custom event payload (optional)
sam local invoke ScraperFunction -e events/scrape.json
```

### Testing the Scraper Lambda (Deployed)

After deploying, you can manually invoke the scraper in AWS:

```bash
# Invoke the deployed scraper Lambda directly
aws lambda invoke \
  --function-name aggiedine-backend-service-ScraperFunction-<suffix> \
  --region us-east-2 \
  --log-type Tail \
  --query 'LogResult' \
  --output text \
  response.json | base64 --decode

# Check the response
cat response.json
```

To find your exact function name:

```bash
aws lambda list-functions --region us-east-2 \
  --query "Functions[?contains(FunctionName, 'Scraper')].FunctionName" \
  --output text
```

After the scraper runs, verify the data was written:

```bash
# Check DynamoDB for scrape records
aws dynamodb scan \
  --table-name <table-name> \
  --region us-east-2 \
  --max-items 5

# Check S3 for cached JSON files
aws s3 ls s3://<bucket-name>/scrapes/ --region us-east-2
```

To find your table and bucket names:

```bash
aws cloudformation describe-stacks \
  --stack-name aggiedine-backend-service \
  --region us-east-2 \
  --query "Stacks[0].Outputs" \
  --output table
```

### Check CloudWatch Logs

```bash
# Tail the scraper logs in real time
aws logs tail /aws/lambda/aggiedine-backend-service-ScraperFunction-<suffix> \
  --region us-east-2 --follow
```

### Testing the API

Get your API URL:

```bash
aws cloudformation describe-stacks \
  --stack-name aggiedine-backend-service \
  --region us-east-2 \
  --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" \
  --output text
```

Then test:

```bash
curl https://<your-api-url>/health
```

## Tear Down

To delete all deployed resources (Lambda, API Gateway, DynamoDB, S3, etc.):

```bash
sam delete --stack-name aggiedine-backend-service
```

This will prompt for confirmation before deleting. Add `--no-prompts` to skip confirmation.

> **Note:** If the S3 bucket has objects in it, you may need to empty it first:
>
> ```bash
> aws s3 rm s3://<bucket-name> --recursive
> ```
>
> Then re-run `sam delete`.
