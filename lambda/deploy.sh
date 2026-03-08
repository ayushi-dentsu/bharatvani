#!/usr/bin/env bash
#
# deploy.sh — Build, push, and deploy the Nova Sonic Health Intake Lambda
#
# Usage:
#   ./deploy.sh                          # Deploy with defaults
#   S3_BUCKET=my-bucket ./deploy.sh      # Override S3 bucket
#
# Prerequisites: AWS CLI v2, Docker, and valid AWS credentials.
#
set -euo pipefail

# ─── Configuration ───────────────────────────────────────────────────────────
AWS_REGION="${AWS_REGION:-us-east-1}"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
FUNCTION_NAME="${FUNCTION_NAME:-nova-sonic-intake}"
ECR_REPO="${ECR_REPO:-nova-sonic-intake}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
S3_BUCKET="${S3_BUCKET:-}"
BEDROCK_MODEL_ID="${BEDROCK_MODEL_ID:-amazon.nova-2-sonic-v1:0}"
VOICE_ID="${VOICE_ID:-arjun}"
ROLE_NAME="${FUNCTION_NAME}-role"
API_NAME="${FUNCTION_NAME}-ws"
MEMORY_SIZE=1024
TIMEOUT=900

ECR_URI="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}"
IMAGE_URI="${ECR_URI}:${IMAGE_TAG}"

echo "==> Deploying ${FUNCTION_NAME} to ${AWS_REGION} (account ${ACCOUNT_ID})"

# ─── 1. Create ECR repository (if needed) ───────────────────────────────────
echo "==> Ensuring ECR repository exists..."
aws ecr describe-repositories --repository-names "${ECR_REPO}" --region "${AWS_REGION}" 2>/dev/null \
  || aws ecr create-repository --repository-name "${ECR_REPO}" --region "${AWS_REGION}"

# ─── 2. Build and push container image ──────────────────────────────────────
echo "==> Logging into ECR..."
aws ecr get-login-password --region "${AWS_REGION}" \
  | docker login --username AWS --password-stdin "${ECR_URI}"

echo "==> Building container image..."
docker build --platform linux/amd64 --provenance=false -t "${ECR_REPO}:${IMAGE_TAG}" .

echo "==> Tagging and pushing..."
docker tag "${ECR_REPO}:${IMAGE_TAG}" "${IMAGE_URI}"
docker push "${IMAGE_URI}"

# ─── 3. Create IAM role (if needed) ─────────────────────────────────────────
ROLE_ARN=""
if aws iam get-role --role-name "${ROLE_NAME}" 2>/dev/null; then
  ROLE_ARN=$(aws iam get-role --role-name "${ROLE_NAME}" --query 'Role.Arn' --output text)
  echo "==> IAM role already exists: ${ROLE_ARN}"
else
  echo "==> Creating IAM role..."
  ASSUME_ROLE_POLICY=$(cat <<'EOF'
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Service": "lambda.amazonaws.com"},
    "Action": "sts:AssumeRole"
  }]
}
EOF
)
  ROLE_ARN=$(aws iam create-role \
    --role-name "${ROLE_NAME}" \
    --assume-role-policy-document "${ASSUME_ROLE_POLICY}" \
    --query 'Role.Arn' --output text)

  # Attach basic Lambda execution
  aws iam attach-role-policy \
    --role-name "${ROLE_NAME}" \
    --policy-arn "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"

  # Inline policy for Bedrock, S3, and API Gateway
  INLINE_POLICY=$(cat <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "bedrock:InvokeModelWithBidirectionalStream",
      "Resource": "arn:aws:bedrock:${AWS_REGION}::foundation-model/*"
    },
    {
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:GetObject"],
      "Resource": "arn:aws:s3:::${S3_BUCKET}/*"
    },
    {
      "Effect": "Allow",
      "Action": "execute-api:ManageConnections",
      "Resource": "arn:aws:execute-api:${AWS_REGION}:${ACCOUNT_ID}:*/@connections/*"
    }
  ]
}
EOF
)
  aws iam put-role-policy \
    --role-name "${ROLE_NAME}" \
    --policy-name "${FUNCTION_NAME}-permissions" \
    --policy-document "${INLINE_POLICY}"

  echo "==> Waiting for role to propagate..."
  sleep 10
fi

# ─── 4. Create or update Lambda function ─────────────────────────────────────
ENV_VARS="{\"Variables\":{\"S3_BUCKET\":\"${S3_BUCKET}\",\"BEDROCK_MODEL_ID\":\"${BEDROCK_MODEL_ID}\",\"VOICE_ID\":\"${VOICE_ID}\"}}"

if aws lambda get-function --function-name "${FUNCTION_NAME}" --region "${AWS_REGION}" 2>/dev/null; then
  echo "==> Updating Lambda function..."
  aws lambda update-function-code \
    --function-name "${FUNCTION_NAME}" \
    --image-uri "${IMAGE_URI}" \
    --region "${AWS_REGION}"

  echo "==> Waiting for update to complete..."
  aws lambda wait function-updated --function-name "${FUNCTION_NAME}" --region "${AWS_REGION}"

  aws lambda update-function-configuration \
    --function-name "${FUNCTION_NAME}" \
    --memory-size ${MEMORY_SIZE} \
    --timeout ${TIMEOUT} \
    --environment "${ENV_VARS}" \
    --region "${AWS_REGION}"
else
  echo "==> Creating Lambda function..."
  aws lambda create-function \
    --function-name "${FUNCTION_NAME}" \
    --package-type Image \
    --code "ImageUri=${IMAGE_URI}" \
    --role "${ROLE_ARN}" \
    --memory-size ${MEMORY_SIZE} \
    --timeout ${TIMEOUT} \
    --environment "${ENV_VARS}" \
    --region "${AWS_REGION}"

  echo "==> Waiting for function to become active..."
  aws lambda wait function-active --function-name "${FUNCTION_NAME}" --region "${AWS_REGION}"
fi

LAMBDA_ARN=$(aws lambda get-function --function-name "${FUNCTION_NAME}" --region "${AWS_REGION}" \
  --query 'Configuration.FunctionArn' --output text)
echo "==> Lambda ARN: ${LAMBDA_ARN}"

# ─── 5. Create API Gateway v2 WebSocket API (if needed) ─────────────────────
API_ID=""
EXISTING_API=$(aws apigatewayv2 get-apis --region "${AWS_REGION}" \
  --query "Items[?Name=='${API_NAME}'].ApiId" --output text 2>/dev/null || true)

if [ -n "${EXISTING_API}" ] && [ "${EXISTING_API}" != "None" ]; then
  API_ID="${EXISTING_API}"
  echo "==> WebSocket API already exists: ${API_ID}"
else
  echo "==> Creating WebSocket API..."
  API_ID=$(aws apigatewayv2 create-api \
    --name "${API_NAME}" \
    --protocol-type WEBSOCKET \
    --route-selection-expression '$request.body.action' \
    --region "${AWS_REGION}" \
    --query 'ApiId' --output text)
fi

# Integration (Lambda proxy)
INTEGRATION_ID=$(aws apigatewayv2 get-integrations --api-id "${API_ID}" --region "${AWS_REGION}" \
  --query 'Items[0].IntegrationId' --output text 2>/dev/null || true)

if [ -z "${INTEGRATION_ID}" ] || [ "${INTEGRATION_ID}" = "None" ]; then
  echo "==> Creating Lambda integration..."
  INTEGRATION_ID=$(aws apigatewayv2 create-integration \
    --api-id "${API_ID}" \
    --integration-type AWS_PROXY \
    --integration-uri "arn:aws:apigateway:${AWS_REGION}:lambda:path/2015-03-31/functions/${LAMBDA_ARN}/invocations" \
    --region "${AWS_REGION}" \
    --query 'IntegrationId' --output text)
fi

# Routes: $connect, $disconnect, $default
for ROUTE_KEY in '$connect' '$disconnect' '$default'; do
  EXISTING_ROUTE=$(aws apigatewayv2 get-routes --api-id "${API_ID}" --region "${AWS_REGION}" \
    --query "Items[?RouteKey=='${ROUTE_KEY}'].RouteId" --output text 2>/dev/null || true)

  if [ -z "${EXISTING_ROUTE}" ] || [ "${EXISTING_ROUTE}" = "None" ]; then
    echo "==> Creating route: ${ROUTE_KEY}"
    aws apigatewayv2 create-route \
      --api-id "${API_ID}" \
      --route-key "${ROUTE_KEY}" \
      --target "integrations/${INTEGRATION_ID}" \
      --region "${AWS_REGION}"
  fi
done

# Grant API Gateway permission to invoke Lambda
aws lambda add-permission \
  --function-name "${FUNCTION_NAME}" \
  --statement-id "apigateway-${API_ID}" \
  --action lambda:InvokeFunction \
  --principal apigateway.amazonaws.com \
  --source-arn "arn:aws:execute-api:${AWS_REGION}:${ACCOUNT_ID}:${API_ID}/*" \
  --region "${AWS_REGION}" 2>/dev/null || true

# Deploy to production stage
EXISTING_STAGE=$(aws apigatewayv2 get-stages --api-id "${API_ID}" --region "${AWS_REGION}" \
  --query "Items[?StageName=='production'].StageName" --output text 2>/dev/null || true)

if [ -z "${EXISTING_STAGE}" ] || [ "${EXISTING_STAGE}" = "None" ]; then
  echo "==> Creating production stage..."
  aws apigatewayv2 create-stage \
    --api-id "${API_ID}" \
    --stage-name production \
    --auto-deploy \
    --region "${AWS_REGION}"
else
  echo "==> Deploying to existing production stage..."
  aws apigatewayv2 create-deployment \
    --api-id "${API_ID}" \
    --stage-name production \
    --region "${AWS_REGION}" 2>/dev/null || true
fi

# ─── Done ────────────────────────────────────────────────────────────────────
WS_URL="wss://${API_ID}.execute-api.${AWS_REGION}.amazonaws.com/production"
echo ""
echo "============================================"
echo "  Deployment complete!"
echo "  WebSocket URL: ${WS_URL}"
echo "============================================"
echo ""
echo "Paste this URL into client/index.html to connect."
