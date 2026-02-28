# Random suffix for S3 bucket names to ensure global uniqueness
resource "random_id" "bucket_suffix" {
  byte_length = 4
}

# Audio Storage Bucket
resource "aws_s3_bucket" "audio_storage" {
  bucket = "${var.project_name}-audio-${var.environment}-${random_id.bucket_suffix.hex}"

  tags = {
    Name        = "${var.project_name}-audio-${var.environment}"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "audio_storage" {
  bucket = aws_s3_bucket.audio_storage.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "audio_storage" {
  bucket = aws_s3_bucket.audio_storage.id

  rule {
    id     = "delete-old-audio"
    status = "Enabled"

    filter {}

    expiration {
      days = 30
    }
  }
}

# ML Models Bucket
resource "aws_s3_bucket" "ml_models" {
  bucket = "${var.project_name}-models-${var.environment}-${random_id.bucket_suffix.hex}"

  tags = {
    Name        = "${var.project_name}-models-${var.environment}"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_s3_bucket_versioning" "ml_models" {
  bucket = aws_s3_bucket.ml_models.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "ml_models" {
  bucket = aws_s3_bucket.ml_models.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# DynamoDB Table for Health Records
resource "aws_dynamodb_table" "health_records" {
  name         = "${var.project_name}-health-records-${var.environment}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "user_id"
  range_key    = "screening_timestamp"

  attribute {
    name = "user_id"
    type = "S"
  }

  attribute {
    name = "screening_timestamp"
    type = "S"
  }

  attribute {
    name = "phone_number"
    type = "S"
  }

  global_secondary_index {
    name            = "phone-index"
    hash_key        = "phone_number"
    projection_type = "ALL"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  tags = {
    Name        = "${var.project_name}-health-records-${var.environment}"
    Environment = var.environment
    Project     = var.project_name
  }
}
