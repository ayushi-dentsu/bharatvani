#!/bin/bash
set -e

echo "=========================================="
echo "Terraform S3 Backend Setup"
echo "=========================================="
echo ""

# Get AWS account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
if [ -z "$ACCOUNT_ID" ]; then
    echo "❌ Error: Unable to get AWS account ID. Please configure AWS credentials first."
    exit 1
fi

echo "✓ AWS Account ID: $ACCOUNT_ID"
echo ""

# Define bucket and table names
BUCKET_NAME="bharatvani-terraform-state-${ACCOUNT_ID}"
TABLE_NAME="bharatvani-terraform-locks"
REGION="ap-south-1"

echo "Creating S3 backend resources:"
echo "  - Bucket: $BUCKET_NAME"
echo "  - DynamoDB Table: $TABLE_NAME"
echo "  - Region: $REGION"
echo ""

# Create S3 bucket
echo "Creating S3 bucket..."
if aws s3 mb s3://${BUCKET_NAME} --region ${REGION} 2>/dev/null; then
    echo "✓ S3 bucket created: ${BUCKET_NAME}"
else
    echo "⚠ S3 bucket already exists or creation failed. Continuing..."
fi

# Enable versioning
echo "Enabling versioning on S3 bucket..."
aws s3api put-bucket-versioning \
    --bucket ${BUCKET_NAME} \
    --versioning-configuration Status=Enabled \
    --region ${REGION}
echo "✓ Versioning enabled"

# Enable encryption
echo "Enabling encryption on S3 bucket..."
aws s3api put-bucket-encryption \
    --bucket ${BUCKET_NAME} \
    --server-side-encryption-configuration '{
        "Rules": [{
            "ApplyServerSideEncryptionByDefault": {
                "SSEAlgorithm": "AES256"
            }
        }]
    }' \
    --region ${REGION}
echo "✓ Encryption enabled"

# Block public access
echo "Blocking public access on S3 bucket..."
aws s3api put-public-access-block \
    --bucket ${BUCKET_NAME} \
    --public-access-block-configuration \
        "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true" \
    --region ${REGION}
echo "✓ Public access blocked"

# Create DynamoDB table for state locking
echo "Creating DynamoDB table for state locking..."
if aws dynamodb create-table \
    --table-name ${TABLE_NAME} \
    --attribute-definitions AttributeName=LockID,AttributeType=S \
    --key-schema AttributeName=LockID,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST \
    --region ${REGION} \
    --tags Key=Project,Value=BharatVani Key=Purpose,Value=TerraformStateLocking \
    >/dev/null 2>&1; then
    echo "✓ DynamoDB table created: ${TABLE_NAME}"
    echo "  Waiting for table to be active..."
    aws dynamodb wait table-exists --table-name ${TABLE_NAME} --region ${REGION}
    echo "✓ Table is active"
else
    echo "⚠ DynamoDB table already exists or creation failed. Continuing..."
fi

echo ""
echo "=========================================="
echo "✓ Backend setup complete!"
echo "=========================================="
echo ""
echo "Backend configuration:"
echo "  Bucket: ${BUCKET_NAME}"
echo "  Table: ${TABLE_NAME}"
echo "  Region: ${REGION}"
echo ""
echo "Next steps:"
echo "  1. Update providers.tf with backend configuration"
echo "  2. Run: terraform init -migrate-state"
echo ""
