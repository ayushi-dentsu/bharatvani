#!/bin/bash

set -e

# Configuration
AWS_REGION="ap-south-1"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REPO_NAME="cough-predictor"
LAMBDA_FUNCTION_NAME="cough-predictor"
IMAGE_TAG="latest"

echo "🚀 Starting deployment of cough-predictor Lambda function..."
echo "AWS Account: $AWS_ACCOUNT_ID"
echo "Region: $AWS_REGION"

# Create or get IAM role for Lambda
echo "🔑 Setting up IAM role..."
ROLE_NAME="cough-predictor-lambda-role"
ROLE_ARN="arn:aws:iam::$AWS_ACCOUNT_ID:role/$ROLE_NAME"

if ! aws iam get-role --role-name $ROLE_NAME 2>/dev/null; then
    echo "📝 Creating IAM role..."
    
    # Create trust policy
    cat > /tmp/trust-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF
    
    aws iam create-role \
        --role-name $ROLE_NAME \
        --assume-role-policy-document file:///tmp/trust-policy.json
    
    # Attach basic execution policy
    aws iam attach-role-policy \
        --role-name $ROLE_NAME \
        --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
    
    # Create and attach S3 access policy for the model bucket
    echo "📝 Creating S3 access policy..."
    cat > /tmp/s3-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::respiratory-ml-models",
        "arn:aws:s3:::respiratory-ml-models/*"
      ]
    }
  ]
}
EOF
    
    aws iam put-role-policy \
        --role-name $ROLE_NAME \
        --policy-name S3ModelAccess \
        --policy-document file:///tmp/s3-policy.json
    
    echo "⏳ Waiting for role to propagate..."
    sleep 10
    
    rm /tmp/trust-policy.json /tmp/s3-policy.json
else
    echo "✓ IAM role already exists"
    
    # Update S3 policy if role exists
    echo "🔄 Updating S3 access policy..."
    cat > /tmp/s3-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::respiratory-ml-models",
        "arn:aws:s3:::respiratory-ml-models/*"
      ]
    }
  ]
}
EOF
    
    aws iam put-role-policy \
        --role-name $ROLE_NAME \
        --policy-name S3ModelAccess \
        --policy-document file:///tmp/s3-policy.json
    
    rm /tmp/s3-policy.json
fi

# Change to ml directory
cd "$(dirname "$0")"

# Download and extract from S3 if not already present
if [ ! -d "cough-predictor" ]; then
    echo "⬇️  Downloading function.zip from S3..."
    aws s3 cp s3://respiratory-ml-models/function.zip.zip function.zip.zip --region $AWS_REGION
    echo "📦 Extracting..."
    unzip -q function.zip.zip
    rm function.zip.zip
else
    echo "✓ cough-predictor directory already exists, skipping download"
fi

# Verify directory exists
if [ ! -d "cough-predictor" ]; then
    echo "❌ Error: cough-predictor directory not found after extraction"
    exit 1
fi

echo "✓ cough-predictor ready ($(du -sh cough-predictor | cut -f1))"

# Create ECR repository if it doesn't exist
echo "📦 Creating ECR repository..."
aws ecr describe-repositories --repository-names $ECR_REPO_NAME --region $AWS_REGION 2>/dev/null || \
    aws ecr create-repository --repository-name $ECR_REPO_NAME --region $AWS_REGION

# Get ECR login
echo "🔐 Logging into ECR..."
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com

# Delete old images from ECR to avoid conflicts
echo "🧹 Cleaning up old images from ECR..."
aws ecr batch-delete-image \
    --repository-name $ECR_REPO_NAME \
    --image-ids imageTag=$IMAGE_TAG \
    --region $AWS_REGION 2>/dev/null || echo "No existing images to delete"

# Remove local Docker images to force rebuild
echo "🧹 Cleaning local Docker cache..."
docker rmi $ECR_REPO_NAME:$IMAGE_TAG 2>/dev/null || true
docker rmi $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_NAME:$IMAGE_TAG 2>/dev/null || true

# Build Docker image for Lambda (x86_64/amd64 platform)
# Disable provenance and attestation to ensure Lambda compatibility
echo "🔨 Building Docker image for x86_64 platform..."
DOCKER_BUILDKIT=1 docker build \
    --no-cache \
    --platform linux/amd64 \
    --provenance=false \
    --output type=docker \
    -t $ECR_REPO_NAME:$IMAGE_TAG .

# Tag image for ECR
echo "🏷️  Tagging image..."
docker tag $ECR_REPO_NAME:$IMAGE_TAG $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_NAME:$IMAGE_TAG

# Push to ECR
echo "⬆️  Pushing image to ECR..."
docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_NAME:$IMAGE_TAG

# Check if Lambda function exists
echo "🔍 Checking if Lambda function exists..."
if aws lambda get-function --function-name $LAMBDA_FUNCTION_NAME --region $AWS_REGION 2>/dev/null; then
    echo "⚠️  Function exists. Checking package type..."
    PACKAGE_TYPE=$(aws lambda get-function-configuration --function-name $LAMBDA_FUNCTION_NAME --region $AWS_REGION --query 'PackageType' --output text)
    
    if [ "$PACKAGE_TYPE" = "Zip" ]; then
        echo "🗑️  Deleting existing Zip-based function to recreate as Image-based..."
        aws lambda delete-function --function-name $LAMBDA_FUNCTION_NAME --region $AWS_REGION
        sleep 5
        
        echo "🆕 Creating new Image-based Lambda function..."
        aws lambda create-function \
            --function-name $LAMBDA_FUNCTION_NAME \
            --package-type Image \
            --code ImageUri=$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_NAME:$IMAGE_TAG \
            --role $ROLE_ARN \
            --timeout 300 \
            --memory-size 2048 \
            --region $AWS_REGION
    else
        echo "♻️  Updating existing Image-based Lambda function..."
        aws lambda update-function-code \
            --function-name $LAMBDA_FUNCTION_NAME \
            --image-uri $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_NAME:$IMAGE_TAG \
            --region $AWS_REGION
        
        # Wait for update to complete
        echo "⏳ Waiting for function update to complete..."
        aws lambda wait function-updated --function-name $LAMBDA_FUNCTION_NAME --region $AWS_REGION
    fi
else
    echo "🆕 Creating new Lambda function..."
    aws lambda create-function \
        --function-name $LAMBDA_FUNCTION_NAME \
        --package-type Image \
        --code ImageUri=$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_NAME:$IMAGE_TAG \
        --role $ROLE_ARN \
        --timeout 300 \
        --memory-size 2048 \
        --region $AWS_REGION
fi

echo "✅ Deployment complete!"
echo "Function ARN: arn:aws:lambda:$AWS_REGION:$AWS_ACCOUNT_ID:function:$LAMBDA_FUNCTION_NAME"
