# IAM Outputs
output "iam_users" {
  description = "IAM usernames created for team members"
  value       = module.iam.iam_usernames
}

output "iam_user_credentials" {
  description = "IAM user access credentials (SENSITIVE - store securely)"
  sensitive   = true
  value       = module.iam.user_credentials
}

# Amazon Connect Outputs (conditional)
output "connect_instance_id" {
  description = "Amazon Connect instance ID (if enabled)"
  value       = var.enable_connect ? module.connect[0].connect_instance_id : null
}

output "connect_phone_number" {
  description = "Phone number for users to call (if enabled)"
  value       = var.enable_connect ? module.connect[0].connect_phone_number : null
}

# Storage Outputs
output "audio_bucket_name" {
  description = "S3 bucket for audio storage"
  value       = module.storage.audio_bucket_name
}

output "models_bucket_name" {
  description = "S3 bucket for ML models"
  value       = module.storage.models_bucket_name
}

output "dynamodb_table_name" {
  description = "DynamoDB table for health records"
  value       = module.storage.dynamodb_table_name
}

# Lambda Outputs
output "audio_processor_lambda_arn" {
  description = "ARN of audio processor Lambda"
  value       = module.lambda.audio_processor_arn
}

output "ml_classifier_lambda_arn" {
  description = "ARN of ML classifier Lambda"
  value       = module.lambda.ml_classifier_arn
}

output "sms_handler_lambda_arn" {
  description = "ARN of SMS handler Lambda"
  value       = module.lambda.sms_handler_arn
}

output "nova_sonic_lambda_arn" {
  description = "ARN of Nova Sonic analyzer Lambda (if enabled)"
  value       = module.lambda.nova_sonic_analyzer_arn
}

# Messaging Outputs
output "sns_topic_arn" {
  description = "SNS topic ARN for SMS"
  value       = module.messaging.sns_topic_arn
}

# Frontend Outputs
output "frontend_url" {
  description = "CloudFront URL for React app (use this to access your dashboard)"
  value       = module.frontend.cloudfront_url
}

output "frontend_bucket_name" {
  description = "S3 bucket name for frontend deployment"
  value       = module.frontend.frontend_bucket_name
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID (for cache invalidation after deployment)"
  value       = module.frontend.cloudfront_distribution_id
}

# SQS Outputs (commented out until Queues module is wired)
# output "sqs_audio_processing_queue_url" {
#   description = "SQS queue URL for audio processing (if enabled)"
#   value       = var.enable_sqs ? module.queues[0].audio_processing_queue_url : null
# }

# output "sqs_ml_results_queue_url" {
#   description = "SQS queue URL for ML results (if enabled)"
#   value       = var.enable_sqs ? module.queues[0].ml_results_queue_url : null
# }

# output "sqs_audio_processing_dlq_url" {
#   description = "SQS DLQ URL for audio processing (if enabled)"
#   value       = var.enable_sqs ? module.queues[0].audio_processing_dlq_url : null
# }

# output "sqs_ml_results_dlq_url" {
#   description = "SQS DLQ URL for ML results (if enabled)"
#   value       = var.enable_sqs ? module.queues[0].ml_results_dlq_url : null
# }
