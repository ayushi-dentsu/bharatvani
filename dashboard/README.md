# BharatVani Dashboard

React dashboard for real-time IVR screening monitoring.

## Setup

```bash
cd dashboard
npm install
cp .env.example .env
# Edit .env with your AWS credentials
npm start
```

## AWS Connection Architecture

```
React App → AWS SDK v3 → AWS Services
    ↓
├─ S3Client → Audio files (presigned URLs)
├─ LambdaClient → ML model invocation
└─ DynamoDBClient → Screening records
```

## Environment Variables

Create `.env` file:
```
REACT_APP_AWS_REGION=ap-south-1
REACT_APP_AWS_ACCESS_KEY_ID=<your-key>
REACT_APP_AWS_SECRET_ACCESS_KEY=<your-secret>
REACT_APP_S3_BUCKET=bharatvani-audio
REACT_APP_LAMBDA_FUNCTION=bharatvani-ml-processor
REACT_APP_DYNAMODB_TABLE=bharatvani-screenings
```

## Deployment

### Option 1: S3 Static Hosting
```bash
npm run build
aws s3 mb s3://bharatvani-dashboard
aws s3 website s3://bharatvani-dashboard --index-document index.html
npm run deploy
```

### Option 2: CloudFront + S3
```bash
npm run build
aws cloudfront create-distribution --origin-domain-name bharatvani-dashboard.s3.amazonaws.com
```

## Git Integration

Add to existing repo:
```bash
cd /Users/harshada/Project/bharatvani
git add dashboard/
git commit -m "Add React dashboard with AWS integration"
git push origin main
```

## IAM Permissions Required

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:ListBucket",
        "lambda:InvokeFunction",
        "dynamodb:Scan",
        "dynamodb:Query",
        "dynamodb:GetItem"
      ],
      "Resource": "*"
    }
  ]
}
```

## Features

- Real-time screening data from DynamoDB
- Audio file access via S3 presigned URLs
- Lambda ML model invocation
- Auto-refresh every 30 seconds
- Risk distribution charts
