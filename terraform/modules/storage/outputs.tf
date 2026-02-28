output "audio_bucket_name" {
  description = "S3 bucket name for audio storage"
  value       = aws_s3_bucket.audio_storage.id
}

output "audio_bucket_arn" {
  description = "S3 bucket ARN for audio storage"
  value       = aws_s3_bucket.audio_storage.arn
}

output "models_bucket_name" {
  description = "S3 bucket name for ML models"
  value       = aws_s3_bucket.ml_models.id
}

output "models_bucket_arn" {
  description = "S3 bucket ARN for ML models"
  value       = aws_s3_bucket.ml_models.arn
}

output "dynamodb_table_name" {
  description = "DynamoDB table name for health records"
  value       = aws_dynamodb_table.health_records.name
}

output "dynamodb_table_arn" {
  description = "DynamoDB table ARN for health records"
  value       = aws_dynamodb_table.health_records.arn
}
