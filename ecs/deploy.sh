#!/usr/bin/env bash
#
# deploy.sh — Build, push, and deploy the Nova Sonic Health Intake to ECS Fargate
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
SERVICE_NAME="${SERVICE_NAME:-nova-sonic-intake}"
ECR_REPO="${ECR_REPO:-nova-sonic-intake-ecs}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
S3_BUCKET="${S3_BUCKET:-}"
BEDROCK_MODEL_ID="${BEDROCK_MODEL_ID:-amazon.nova-2-sonic-v1:0}"
VOICE_ID="${VOICE_ID:-arjun}"
CLUSTER_NAME="${SERVICE_NAME}-cluster"
TASK_FAMILY="${SERVICE_NAME}-task"
CONTAINER_NAME="${SERVICE_NAME}"
CONTAINER_PORT=8080
CPU=1024        # 1 vCPU
MEMORY=2048     # 2 GB
ROLE_NAME="${SERVICE_NAME}-ecs-role"

ECR_URI="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}"
IMAGE_URI="${ECR_URI}:${IMAGE_TAG}"

echo "==> Deploying ${SERVICE_NAME} to ECS Fargate in ${AWS_REGION} (account ${ACCOUNT_ID})"

# ─── 1. Create ECR repository (if needed) ───────────────────────────────────
echo "==> Ensuring ECR repository exists..."
aws ecr describe-repositories --repository-names "${ECR_REPO}" --region "${AWS_REGION}" 2>/dev/null \
  || aws ecr create-repository --repository-name "${ECR_REPO}" --region "${AWS_REGION}"

# ─── 2. Build and push container image ──────────────────────────────────────
echo "==> Logging into ECR..."
aws ecr get-login-password --region "${AWS_REGION}" \
  | docker login --username AWS --password-stdin "${ECR_URI}"

echo "==> Building container image..."
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
docker build --platform linux/amd64 --provenance=false -t "${ECR_REPO}:${IMAGE_TAG}" "${SCRIPT_DIR}"

echo "==> Tagging and pushing..."
docker tag "${ECR_REPO}:${IMAGE_TAG}" "${IMAGE_URI}"
docker push "${IMAGE_URI}"

# ─── 3. Create IAM roles ────────────────────────────────────────────────────
# Task execution role (for ECS to pull images and write logs)
EXEC_ROLE_NAME="${SERVICE_NAME}-exec-role"
EXEC_ROLE_ARN=""
if aws iam get-role --role-name "${EXEC_ROLE_NAME}" 2>/dev/null; then
  EXEC_ROLE_ARN=$(aws iam get-role --role-name "${EXEC_ROLE_NAME}" --query 'Role.Arn' --output text)
  echo "==> Execution role exists: ${EXEC_ROLE_ARN}"
else
  echo "==> Creating ECS task execution role..."
  EXEC_ROLE_ARN=$(aws iam create-role \
    --role-name "${EXEC_ROLE_NAME}" \
    --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ecs-tasks.amazonaws.com"},"Action":"sts:AssumeRole"}]}' \
    --query 'Role.Arn' --output text)
  aws iam attach-role-policy \
    --role-name "${EXEC_ROLE_NAME}" \
    --policy-arn "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
fi

# Task role (for the container to access Bedrock, S3, etc.)
TASK_ROLE_ARN=""
if aws iam get-role --role-name "${ROLE_NAME}" 2>/dev/null; then
  TASK_ROLE_ARN=$(aws iam get-role --role-name "${ROLE_NAME}" --query 'Role.Arn' --output text)
  echo "==> Task role exists: ${TASK_ROLE_ARN}"
else
  echo "==> Creating ECS task role..."
  TASK_ROLE_ARN=$(aws iam create-role \
    --role-name "${ROLE_NAME}" \
    --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ecs-tasks.amazonaws.com"},"Action":"sts:AssumeRole"}]}' \
    --query 'Role.Arn' --output text)

  INLINE_POLICY=$(cat <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream",
        "bedrock:InvokeModelWithBidirectionalStream"
      ],
      "Resource": "arn:aws:bedrock:${AWS_REGION}::foundation-model/*"
    },
    {
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:GetObject"],
      "Resource": "arn:aws:s3:::${S3_BUCKET}/*"
    }
  ]
}
EOF
)
  aws iam put-role-policy \
    --role-name "${ROLE_NAME}" \
    --policy-name "${SERVICE_NAME}-permissions" \
    --policy-document "${INLINE_POLICY}"

  echo "==> Waiting for roles to propagate..."
  sleep 10
fi

# ─── 4. Create ECS cluster (if needed) ──────────────────────────────────────
echo "==> Ensuring ECS cluster exists..."
aws ecs describe-clusters --clusters "${CLUSTER_NAME}" --region "${AWS_REGION}" \
  --query 'clusters[?status==`ACTIVE`].clusterName' --output text 2>/dev/null | grep -q "${CLUSTER_NAME}" \
  || aws ecs create-cluster --cluster-name "${CLUSTER_NAME}" --region "${AWS_REGION}"

# ─── 5. Create CloudWatch log group ─────────────────────────────────────────
LOG_GROUP="/ecs/${SERVICE_NAME}"
aws logs create-log-group --log-group-name "${LOG_GROUP}" --region "${AWS_REGION}" 2>/dev/null || true

# ─── 6. Register task definition ────────────────────────────────────────────
echo "==> Registering task definition..."
TASK_DEF=$(cat <<EOF
{
  "family": "${TASK_FAMILY}",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "${CPU}",
  "memory": "${MEMORY}",
  "executionRoleArn": "${EXEC_ROLE_ARN}",
  "taskRoleArn": "${TASK_ROLE_ARN}",
  "containerDefinitions": [
    {
      "name": "${CONTAINER_NAME}",
      "image": "${IMAGE_URI}",
      "essential": true,
      "portMappings": [
        {
          "containerPort": ${CONTAINER_PORT},
          "protocol": "tcp"
        }
      ],
      "environment": [
        {"name": "S3_BUCKET", "value": "${S3_BUCKET}"},
        {"name": "BEDROCK_MODEL_ID", "value": "${BEDROCK_MODEL_ID}"},
        {"name": "VOICE_ID", "value": "${VOICE_ID}"},
        {"name": "PORT", "value": "${CONTAINER_PORT}"}
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "${LOG_GROUP}",
          "awslogs-region": "${AWS_REGION}",
          "awslogs-stream-prefix": "ecs"
        }
      }
    }
  ]
}
EOF
)

aws ecs register-task-definition \
  --cli-input-json "${TASK_DEF}" \
  --region "${AWS_REGION}" > /dev/null

# ─── 7. Get default VPC and subnets ─────────────────────────────────────────
echo "==> Finding default VPC and subnets..."
VPC_ID=$(aws ec2 describe-vpcs --filters "Name=isDefault,Values=true" \
  --region "${AWS_REGION}" --query 'Vpcs[0].VpcId' --output text)

SUBNETS=$(aws ec2 describe-subnets --filters "Name=vpc-id,Values=${VPC_ID}" \
  --region "${AWS_REGION}" --query 'Subnets[*].SubnetId' --output text | tr '\t' ',')

# ─── 8. Create security group ───────────────────────────────────────────────
SG_NAME="${SERVICE_NAME}-sg"
SG_ID=$(aws ec2 describe-security-groups \
  --filters "Name=group-name,Values=${SG_NAME}" "Name=vpc-id,Values=${VPC_ID}" \
  --region "${AWS_REGION}" --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null || echo "None")

if [ "${SG_ID}" = "None" ] || [ -z "${SG_ID}" ]; then
  echo "==> Creating security group..."
  SG_ID=$(aws ec2 create-security-group \
    --group-name "${SG_NAME}" \
    --description "Security group for ${SERVICE_NAME} ECS service" \
    --vpc-id "${VPC_ID}" \
    --region "${AWS_REGION}" \
    --query 'GroupId' --output text)

  aws ec2 authorize-security-group-ingress \
    --group-id "${SG_ID}" \
    --protocol tcp \
    --port ${CONTAINER_PORT} \
    --cidr 0.0.0.0/0 \
    --region "${AWS_REGION}"
  echo "==> Security group created: ${SG_ID}"
else
  echo "==> Security group exists: ${SG_ID}"
fi

# ─── 9. Create or update ECS service ────────────────────────────────────────
EXISTING_SERVICE=$(aws ecs describe-services \
  --cluster "${CLUSTER_NAME}" \
  --services "${SERVICE_NAME}" \
  --region "${AWS_REGION}" \
  --query 'services[?status==`ACTIVE`].serviceName' --output text 2>/dev/null || true)

if [ -n "${EXISTING_SERVICE}" ] && [ "${EXISTING_SERVICE}" != "None" ]; then
  echo "==> Updating ECS service..."
  aws ecs update-service \
    --cluster "${CLUSTER_NAME}" \
    --service "${SERVICE_NAME}" \
    --task-definition "${TASK_FAMILY}" \
    --force-new-deployment \
    --region "${AWS_REGION}" > /dev/null
else
  echo "==> Creating ECS service..."
  aws ecs create-service \
    --cluster "${CLUSTER_NAME}" \
    --service-name "${SERVICE_NAME}" \
    --task-definition "${TASK_FAMILY}" \
    --desired-count 1 \
    --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[${SUBNETS}],securityGroups=[${SG_ID}],assignPublicIp=ENABLED}" \
    --region "${AWS_REGION}" > /dev/null
fi

# ─── 10. Wait for service to stabilize and get public IP ────────────────────
echo "==> Waiting for service to stabilize (this may take a few minutes)..."
aws ecs wait services-stable \
  --cluster "${CLUSTER_NAME}" \
  --services "${SERVICE_NAME}" \
  --region "${AWS_REGION}" 2>/dev/null || true

# Get the task's public IP
TASK_ARN=$(aws ecs list-tasks \
  --cluster "${CLUSTER_NAME}" \
  --service-name "${SERVICE_NAME}" \
  --region "${AWS_REGION}" \
  --query 'taskArns[0]' --output text)

ENI_ID=$(aws ecs describe-tasks \
  --cluster "${CLUSTER_NAME}" \
  --tasks "${TASK_ARN}" \
  --region "${AWS_REGION}" \
  --query 'tasks[0].attachments[0].details[?name==`networkInterfaceId`].value' --output text)

PUBLIC_IP=$(aws ec2 describe-network-interfaces \
  --network-interface-ids "${ENI_ID}" \
  --region "${AWS_REGION}" \
  --query 'NetworkInterfaces[0].Association.PublicIp' --output text)

# ─── Done ────────────────────────────────────────────────────────────────────
WS_URL="ws://${PUBLIC_IP}:${CONTAINER_PORT}"

# Auto-patch client/index.html with the new WebSocket URL
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CLIENT_HTML="${SCRIPT_DIR}/../client/index.html"
if [ -f "${CLIENT_HTML}" ]; then
  sed -i.bak "s|value=\"ws://[^\"]*\"|value=\"${WS_URL}\"|g" "${CLIENT_HTML}"
  rm -f "${CLIENT_HTML}.bak"
  echo "==> Updated client/index.html with WebSocket URL"
fi

echo ""
echo "============================================"
echo "  ECS Deployment complete!"
echo "  WebSocket URL: ${WS_URL}"
echo "  Cluster: ${CLUSTER_NAME}"
echo "  Service: ${SERVICE_NAME}"
echo "============================================"
