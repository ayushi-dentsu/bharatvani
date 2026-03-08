#!/usr/bin/env bash
#
# deploy.sh — Build, push, and deploy the Audio Predictor Lambda
#
set -euo pipefail
export AWS_PAGER=""

AWS_REGION="${AWS_REGION:-us-east-1}"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
FUNCTION_NAME="${FUNCTION_NAME:-bharatvani-audio-predictor}"
ECR_REPO="${ECR_REPO:-bharatvani-audio-predictor}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
SCREENING_TABLE="${SCREENING_TABLE:-bharatvani-screenings}"
S3_BUCKET="${S3_BUCKET:-ivr-call-recordings-797882812707-us-east-1}"
ROLE_NAME="${FUNCTION_NAME}-role"

ECR_URI="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}"
IMAGE_URI="${ECR_URI}:${IMAGE_TAG}"

echo "==> Deploying ${FUNCTION_NAME} to ${AWS_REGION} (account ${ACCOUNT_ID})"

# ─── 1. ECR repository ──────────────────────────────────────────────────────
echo "==> Ensuring ECR repository exists..."
aws ecr describe-repositories --repository-names "${ECR_REPO}" --region "${AWS_REGION}" > /dev/null 2>&1 \
  || aws ecr create-repository --repository-name "${ECR_REPO}" --region "${AWS_REGION}" > /dev/null

# ─── 2. Build and push ──────────────────────────────────────────────────────
echo "==> Logging into ECR..."
aws ecr get-login-password --region "${AWS_REGION}" \
  | docker login --username AWS --password-stdin "${ECR_URI}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "==> Building container image..."
docker build --platform linux/amd64 --provenance=false -t "${ECR_REPO}:${IMAGE_TAG}" "${SCRIPT_DIR}"

echo "==> Pushing to ECR..."
docker tag "${ECR_REPO}:${IMAGE_TAG}" "${IMAGE_URI}"
docker push "${IMAGE_URI}"

# ─── 3. IAM role ────────────────────────────────────────────────────────────
echo "==> Setting up IAM role..."
if aws iam get-role --role-name "${ROLE_NAME}" > /dev/null 2>&1; then
  ROLE_ARN=$(aws iam get-role --role-name "${ROLE_NAME}" --query 'Role.Arn' --output text)
  echo "==> IAM role exists"
else
  echo "==> Creating IAM role..."
  ROLE_ARN=$(aws iam create-role \
    --role-name "${ROLE_NAME}" \
    --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}' \
    --query 'Role.Arn' --output text)

  aws iam attach-role-policy --role-name "${ROLE_NAME}" \
    --policy-arn "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"

  aws iam put-role-policy --role-name "${ROLE_NAME}" \
    --policy-name "${FUNCTION_NAME}-permissions" \
    --policy-document "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":[\"s3:GetObject\"],\"Resource\":[\"arn:aws:s3:::${S3_BUCKET}/*\",\"arn:aws:s3:::respiratory-ml-models/*\"]},{\"Effect\":\"Allow\",\"Action\":[\"dynamodb:UpdateItem\",\"dynamodb:GetItem\"],\"Resource\":\"arn:aws:dynamodb:${AWS_REGION}:${ACCOUNT_ID}:table/${SCREENING_TABLE}\"}]}"

  echo "==> Waiting for role to propagate..."
  sleep 10
fi

# ─── 4. Create or update Lambda ─────────────────────────────────────────────
ENV_VARS="{\"Variables\":{\"SCREENING_TABLE\":\"${SCREENING_TABLE}\",\"NUMBA_CACHE_DIR\":\"/tmp\"}}"

if aws lambda get-function --function-name "${FUNCTION_NAME}" --region "${AWS_REGION}" > /dev/null 2>&1; then
  echo "==> Updating Lambda function..."
  aws lambda update-function-code \
    --function-name "${FUNCTION_NAME}" \
    --image-uri "${IMAGE_URI}" \
    --region "${AWS_REGION}" > /dev/null

  aws lambda wait function-updated --function-name "${FUNCTION_NAME}" --region "${AWS_REGION}"

  aws lambda update-function-configuration \
    --function-name "${FUNCTION_NAME}" \
    --memory-size 1024 \
    --timeout 60 \
    --environment "${ENV_VARS}" \
    --region "${AWS_REGION}" > /dev/null
else
  echo "==> Creating Lambda function..."
  aws lambda create-function \
    --function-name "${FUNCTION_NAME}" \
    --package-type Image \
    --code "ImageUri=${IMAGE_URI}" \
    --role "${ROLE_ARN}" \
    --memory-size 1024 \
    --timeout 60 \
    --environment "${ENV_VARS}" \
    --region "${AWS_REGION}" > /dev/null

  aws lambda wait function-active --function-name "${FUNCTION_NAME}" --region "${AWS_REGION}"
fi

echo "==> Lambda deployed"

echo ""
echo "============================================"
echo "  Audio Predictor deployed!"
echo "  Function: ${FUNCTION_NAME}"
echo "  NOTE: S3 triggers are managed separately."
echo "============================================"
