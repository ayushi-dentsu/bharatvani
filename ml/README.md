# Cough Predictor Lambda Deployment

This directory contains the Docker configuration for deploying the cough-predictor Lambda function as a container image.

## Prerequisites

- Docker installed and running
- AWS CLI configured with appropriate credentials
- Permissions for ECR, Lambda, and IAM

## Deployment Steps

1. Make sure Docker is running
2. Ensure AWS CLI is configured with credentials that have access to the S3 bucket
3. Run the deployment script:
   ```bash
   ./ml/deploy-cough-predictor.sh
   ```

The script will automatically download the function.zip from S3 if not already present.

## What the Script Does

1. Creates an ECR repository named `cough-predictor`
2. Builds a Docker image from the S3-hosted function code
3. Pushes the image to ECR
4. Creates or updates the Lambda function with the container image

## Configuration

The function is deployed with:
- Memory: 2048 MB
- Timeout: 300 seconds (5 minutes)
- Region: ap-south-1

## Customization

If you need to modify the handler or add dependencies, edit the `Dockerfile`:
- Change the CMD line to point to your handler
- Add pip install commands for additional Python packages
- Install system dependencies with yum

## Troubleshooting

If the Lambda function creation fails due to missing IAM role, create one:
```bash
aws iam create-role --role-name lambda-execution-role \
  --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}'

aws iam attach-role-policy --role-name lambda-execution-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
```
