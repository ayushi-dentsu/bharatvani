#!/bin/bash

set -e

# Configuration
AWS_REGION="us-east-1"
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

# Check if there's an existing cough-predictor role
EXISTING_ROLE=$(aws iam list-roles --query 'Roles[?contains(RoleName, `cough-predictor`)].RoleName' --output text | head -n1)
if [ -n "$EXISTING_ROLE" ]; then
    echo "✓ Found existing role: $EXISTING_ROLE"
    ROLE_NAME="$EXISTING_ROLE"
    # Get the full ARN including any path
    ROLE_ARN=$(aws iam get-role --role-name "$ROLE_NAME" --query 'Role.Arn' --output text)
    echo "Using ARN: $ROLE_ARN"
else
    ROLE_ARN="arn:aws:iam::$AWS_ACCOUNT_ID:role/$ROLE_NAME"
fi

if aws iam get-role --role-name $ROLE_NAME &>/dev/null; then
    echo "✓ IAM role already exists"
else
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
        "arn:aws:s3:::respiratory-ml-models/*",
        "arn:aws:s3:::ivr-call-recordings-797882812707-us-east-1",
        "arn:aws:s3:::ivr-call-recordings-797882812707-us-east-1/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:UpdateItem",
        "dynamodb:GetItem"
      ],
      "Resource": "arn:aws:dynamodb:us-east-1:$AWS_ACCOUNT_ID:table/bharatvani-screenings"
    }
  ]
}
EOF
    
    aws iam put-role-policy \
        --role-name $ROLE_NAME \
        --policy-name S3ModelAccess \
        --policy-document file:///tmp/s3-policy.json
    
    echo "⏳ Waiting for role to propagate..."
    sleep 15
    
    rm /tmp/trust-policy.json /tmp/s3-policy.json
fi

# Update policies if role exists
if aws iam get-role --role-name $ROLE_NAME &>/dev/null; then
    echo "🔄 Updating access policies..."
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
        "arn:aws:s3:::respiratory-ml-models/*",
        "arn:aws:s3:::ivr-call-recordings-797882812707-us-east-1",
        "arn:aws:s3:::ivr-call-recordings-797882812707-us-east-1/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:UpdateItem",
        "dynamodb:GetItem"
      ],
      "Resource": "arn:aws:dynamodb:us-east-1:$AWS_ACCOUNT_ID:table/bharatvani-screenings"
    }
  ]
}
EOF
    
    aws iam put-role-policy \
        --role-name $ROLE_NAME \
        --policy-name S3ModelAccess \
        --policy-document file:///tmp/s3-policy.json
    
    # Ensure trust policy is correct
    echo "🔄 Updating trust policy..."
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
    
    aws iam update-assume-role-policy \
        --role-name $ROLE_NAME \
        --policy-document file:///tmp/trust-policy.json
    
    rm /tmp/s3-policy.json /tmp/trust-policy.json
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
echo "📦 Checking ECR repository..."
if aws ecr describe-repositories --repository-names $ECR_REPO_NAME --region $AWS_REGION &>/dev/null; then
    echo "✓ ECR repository already exists"
else
    echo "Creating ECR repository..."
    aws ecr create-repository --repository-name $ECR_REPO_NAME --region $AWS_REGION
fi

# Get ECR login
echo "🔐 Logging into ECR..."
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com

# Check if image already exists in ECR
echo "🔍 Checking if image already exists in ECR..."
if aws ecr describe-images --repository-name $ECR_REPO_NAME --image-ids imageTag=$IMAGE_TAG --region $AWS_REGION &>/dev/null; then
    echo "✓ Image already exists in ECR, skipping build and push"
    SKIP_BUILD=true
else
    echo "Image not found in ECR, will build and push"
    SKIP_BUILD=false
fi

if [ "$SKIP_BUILD" = false ]; then
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
fi

# Ensure IAM role is ready
echo "⏳ Ensuring IAM role is ready..."
sleep 10

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
        RETRIES=0
        MAX_RETRIES=5
        while [ $RETRIES -lt $MAX_RETRIES ]; do
            if aws lambda create-function \
                --function-name $LAMBDA_FUNCTION_NAME \
                --package-type Image \
                --code ImageUri=$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_NAME:$IMAGE_TAG \
                --role $ROLE_ARN \
                --timeout 300 \
                --memory-size 2048 \
                --environment '{"Variables":{"SCREENING_TABLE":"bharatvani-screenings"}}' \
                --region $AWS_REGION 2>&1; then
                echo "✅ Function created successfully"
                break
            else
                RETRIES=$((RETRIES + 1))
                if [ $RETRIES -lt $MAX_RETRIES ]; then
                    WAIT_TIME=$((5 * RETRIES))
                    echo "⏳ Waiting ${WAIT_TIME}s for IAM role to propagate (attempt $RETRIES/$MAX_RETRIES)..."
                    sleep $WAIT_TIME
                else
                    echo "❌ Failed to create function after $MAX_RETRIES attempts"
                    exit 1
                fi
            fi
        done
    else
        echo "♻️  Updating existing Image-based Lambda function..."
        aws lambda update-function-code \
            --function-name $LAMBDA_FUNCTION_NAME \
            --image-uri $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_NAME:$IMAGE_TAG \
            --region $AWS_REGION
        
        # Wait for update to complete
        echo "⏳ Waiting for function update to complete..."
        aws lambda wait function-updated --function-name $LAMBDA_FUNCTION_NAME --region $AWS_REGION

        # Update environment variables
        aws lambda update-function-configuration \
            --function-name $LAMBDA_FUNCTION_NAME \
            --environment '{"Variables":{"SCREENING_TABLE":"bharatvani-screenings"}}' \
            --region $AWS_REGION
    fi
else
    echo "🆕 Creating new Lambda function..."
    RETRIES=0
    MAX_RETRIES=5
    while [ $RETRIES -lt $MAX_RETRIES ]; do
        if aws lambda create-function \
            --function-name $LAMBDA_FUNCTION_NAME \
            --package-type Image \
            --code ImageUri=$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_NAME:$IMAGE_TAG \
            --role $ROLE_ARN \
            --timeout 300 \
            --memory-size 2048 \
            --environment '{"Variables":{"SCREENING_TABLE":"bharatvani-screenings"}}' \
            --region $AWS_REGION 2>&1; then
            echo "✅ Function created successfully"
            break
        else
            RETRIES=$((RETRIES + 1))
            if [ $RETRIES -lt $MAX_RETRIES ]; then
                WAIT_TIME=$((5 * RETRIES))
                echo "⏳ Waiting ${WAIT_TIME}s for IAM role to propagate (attempt $RETRIES/$MAX_RETRIES)..."
                sleep $WAIT_TIME
            else
                echo "❌ Failed to create function after $MAX_RETRIES attempts"
                exit 1
            fi
        fi
    done
fi

echo "✅ Deployment complete!"
echo "Function ARN: arn:aws:lambda:$AWS_REGION:$AWS_ACCOUNT_ID:function:$LAMBDA_FUNCTION_NAME"
