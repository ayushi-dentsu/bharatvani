#!/usr/bin/env bash
#
# deploy_aggregator.sh — Deploy the Screening Aggregator Lambda + DynamoDB Stream trigger
#
set -euo pipefail

AWS_REGION="${AWS_REGION:-us-east-1}"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
FUNCTION_NAME="${FUNCTION_NAME:-bharatvani-screening-aggregator}"
SCREENING_TABLE="${SCREENING_TABLE:-bharatvani-screenings}"
BEDROCK_MODEL_ID="${BEDROCK_MODEL_ID:-anthropic.claude-3-haiku-20240307-v1:0}"
ROLE_NAME="${FUNCTION_NAME}-role"

echo "==> Deploying ${FUNCTION_NAME} to ${AWS_REGION} (account ${ACCOUNT_ID})"

# ─── 1. Enable DynamoDB Streams ─────────────────────────────────────────────
echo "==> Enabling DynamoDB Streams on ${SCREENING_TABLE}..."
STREAM_STATUS=$(aws dynamodb describe-table \
  --table-name "${SCREENING_TABLE}" --region "${AWS_REGION}" \
  --query 'Table.StreamSpecification.StreamEnabled' --output text 2>/dev/null || echo "None")

if [ "${STREAM_STATUS}" != "True" ]; then
  aws dynamodb update-table \
    --table-name "${SCREENING_TABLE}" \
    --stream-specification StreamEnabled=true,StreamViewType=NEW_IMAGE \
    --region "${AWS_REGION}"
  echo "==> Waiting for table to be active..."
  aws dynamodb wait table-exists --table-name "${SCREENING_TABLE}" --region "${AWS_REGION}"
else
  echo "==> DynamoDB Streams already enabled"
fi

STREAM_ARN=$(aws dynamodb describe-table \
  --table-name "${SCREENING_TABLE}" --region "${AWS_REGION}" \
  --query 'Table.LatestStreamArn' --output text)
echo "==> Stream ARN: ${STREAM_ARN}"

# ─── 2. Create IAM role ─────────────────────────────────────────────────────
echo "==> Setting up IAM role..."
if aws iam get-role --role-name "${ROLE_NAME}" > /dev/null 2>&1; then
  ROLE_ARN=$(aws iam get-role --role-name "${ROLE_NAME}" --query 'Role.Arn' --output text)
  echo "==> IAM role exists: ${ROLE_ARN}"
else
  echo "==> Creating IAM role..."
  ROLE_ARN=$(aws iam create-role \
    --role-name "${ROLE_NAME}" \
    --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}' \
    --query 'Role.Arn' --output text)

  aws iam attach-role-policy \
    --role-name "${ROLE_NAME}" \
    --policy-arn "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"

  aws iam attach-role-policy \
    --role-name "${ROLE_NAME}" \
    --policy-arn "arn:aws:iam::aws:policy/service-role/AWSLambdaDynamoDBExecutionRole"

  aws iam put-role-policy \
    --role-name "${ROLE_NAME}" \
    --policy-name "${FUNCTION_NAME}-permissions" \
    --policy-document "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":[\"bedrock:InvokeModel\"],\"Resource\":\"arn:aws:bedrock:${AWS_REGION}::foundation-model/*\"},{\"Effect\":\"Allow\",\"Action\":[\"dynamodb:GetItem\",\"dynamodb:PutItem\",\"dynamodb:UpdateItem\",\"dynamodb:Query\"],\"Resource\":\"arn:aws:dynamodb:${AWS_REGION}:${ACCOUNT_ID}:table/${SCREENING_TABLE}\"}]}"

  echo "==> Waiting for role to propagate..."
  sleep 10
fi

echo "==> ROLE_ARN set"

# ─── 3. Package Lambda function ─────────────────────────────────────────────
echo "==> Packaging Lambda function..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_DIR=$(mktemp -d)
cp "${SCRIPT_DIR}/screening_aggregator.py" "${PACKAGE_DIR}/screening_aggregator.py"
cd "${PACKAGE_DIR}"
zip -r function.zip screening_aggregator.py
cd "${SCRIPT_DIR}"

# ─── 4. Create or update Lambda function ────────────────────────────────────
ENV_VARS="{\"Variables\":{\"SCREENING_TABLE\":\"${SCREENING_TABLE}\",\"BEDROCK_MODEL_ID\":\"${BEDROCK_MODEL_ID}\"}}"

if aws lambda get-function --function-name "${FUNCTION_NAME}" --region "${AWS_REGION}" > /dev/null 2>&1; then
  echo "==> Updating Lambda function code..."
  aws lambda update-function-code \
    --function-name "${FUNCTION_NAME}" \
    --zip-file "fileb://${PACKAGE_DIR}/function.zip" \
    --region "${AWS_REGION}"

  echo "==> Waiting for update..."
  aws lambda wait function-updated --function-name "${FUNCTION_NAME}" --region "${AWS_REGION}"

  aws lambda update-function-configuration \
    --function-name "${FUNCTION_NAME}" \
    --memory-size 256 \
    --timeout 60 \
    --environment "${ENV_VARS}" \
    --region "${AWS_REGION}"
else
  echo "==> Creating Lambda function..."
  aws lambda create-function \
    --function-name "${FUNCTION_NAME}" \
    --runtime python3.12 \
    --handler screening_aggregator.lambda_handler \
    --role "${ROLE_ARN}" \
    --zip-file "fileb://${PACKAGE_DIR}/function.zip" \
    --memory-size 256 \
    --timeout 60 \
    --environment "${ENV_VARS}" \
    --region "${AWS_REGION}"

  echo "==> Waiting for function to become active..."
  aws lambda wait function-active --function-name "${FUNCTION_NAME}" --region "${AWS_REGION}"
fi

LAMBDA_ARN=$(aws lambda get-function --function-name "${FUNCTION_NAME}" --region "${AWS_REGION}" \
  --query 'Configuration.FunctionArn' --output text)
echo "==> Lambda ARN: ${LAMBDA_ARN}"

# ─── 5. Create DynamoDB Stream event source mapping ─────────────────────────
EXISTING_MAPPING=$(aws lambda list-event-source-mappings \
  --function-name "${FUNCTION_NAME}" --region "${AWS_REGION}" \
  --query "EventSourceMappings[?contains(EventSourceArn, '${SCREENING_TABLE}')].UUID" \
  --output text 2>/dev/null || true)

if [ -z "${EXISTING_MAPPING}" ] || [ "${EXISTING_MAPPING}" = "None" ]; then
  echo "==> Creating DynamoDB Stream event source mapping..."
  aws lambda create-event-source-mapping \
    --function-name "${FUNCTION_NAME}" \
    --event-source-arn "${STREAM_ARN}" \
    --starting-position LATEST \
    --batch-size 1 \
    --region "${AWS_REGION}"
else
  echo "==> Event source mapping already exists: ${EXISTING_MAPPING}"
fi

# ─── Cleanup ─────────────────────────────────────────────────────────────────
rm -rf "${PACKAGE_DIR}"

echo ""
echo "============================================"
echo "  Screening Aggregator deployed!"
echo "  Function: ${FUNCTION_NAME}"
echo "  Table:    ${SCREENING_TABLE}"
echo "  Stream:   ${STREAM_ARN}"
echo "============================================"
