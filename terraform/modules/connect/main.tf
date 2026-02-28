# Provider configuration for Connect (must use supported region)
terraform {
  required_providers {
    aws = {
      source                = "hashicorp/aws"
      version               = ">= 5.0"
      configuration_aliases = [aws.connect]
    }
  }
}

# Amazon Connect Instance
resource "aws_connect_instance" "bharatvani" {
  provider = aws.connect

  identity_management_type = "CONNECT_MANAGED"
  inbound_calls_enabled    = true
  outbound_calls_enabled   = false
  instance_alias           = "${var.project_name}-${var.environment}"

  tags = {
    Name        = "BharatVani Connect Instance"
    Environment = var.environment
    Project     = var.project_name
  }
}

# Configure S3 storage for call recordings
resource "aws_connect_instance_storage_config" "call_recordings" {
  provider = aws.connect

  instance_id   = aws_connect_instance.bharatvani.id
  resource_type = "CALL_RECORDINGS"

  storage_config {
    storage_type = "S3"

    s3_config {
      bucket_name   = var.audio_bucket_id
      bucket_prefix = "recordings/"

      encryption_config {
        encryption_type = "KMS"
        key_id          = data.aws_kms_alias.s3.target_key_arn
      }
    }
  }
}

# Data source to get AWS managed S3 KMS key ARN
data "aws_kms_alias" "s3" {
  provider = aws.connect
  name     = "alias/aws/s3"
}

# Configure S3 storage for contact trace records (optional, for debugging)
resource "aws_connect_instance_storage_config" "contact_trace_records" {
  provider = aws.connect

  instance_id   = aws_connect_instance.bharatvani.id
  resource_type = "CONTACT_TRACE_RECORDS"

  storage_config {
    storage_type = "S3"

    s3_config {
      bucket_name   = var.audio_bucket_id
      bucket_prefix = "contact-traces/"
    }
  }
}

# Provision Indian toll-free phone number
resource "aws_connect_phone_number" "bharatvani" {
  provider = aws.connect

  country_code = "IN"
  type         = "TOLL_FREE"
  target_arn   = aws_connect_instance.bharatvani.arn

  tags = {
    Name        = "BharatVani Toll-Free Number"
    Environment = var.environment
    Project     = var.project_name
  }
}

# IAM role for Connect to access S3
resource "aws_iam_role" "connect_s3_access" {
  provider = aws.connect

  name = "${var.project_name}-connect-s3-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "connect.amazonaws.com"
      }
    }]
  })

  tags = {
    Name        = "BharatVani Connect S3 Access Role"
    Environment = var.environment
    Project     = var.project_name
  }
}

# IAM policy for Connect S3 access
resource "aws_iam_role_policy" "connect_s3_policy" {
  provider = aws.connect

  name = "${var.project_name}-connect-s3-policy"
  role = aws_iam_role.connect_s3_access.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:PutObjectAcl",
          "s3:GetObject",
          "s3:GetObjectAcl"
        ]
        Resource = "${var.audio_bucket_arn}/*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetBucketLocation",
          "s3:GetBucketAcl"
        ]
        Resource = var.audio_bucket_arn
      }
    ]
  })
}
