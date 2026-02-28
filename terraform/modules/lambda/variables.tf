variable "environment" {
  description = "Environment name (dev/demo/prod)"
  type        = string
}

variable "project_name" {
  description = "Project name for resource tagging"
  type        = string
}

variable "audio_bucket_name" {
  description = "S3 bucket name for audio storage"
  type        = string
}

variable "models_bucket_name" {
  description = "S3 bucket name for ML models"
  type        = string
}

variable "dynamodb_table_name" {
  description = "DynamoDB table name for health records"
  type        = string
}

variable "sns_topic_arn" {
  description = "SNS topic ARN for SMS notifications"
  type        = string
}

variable "enable_nova_sonic" {
  description = "Enable Amazon Nova Sonic for AI-powered audio analysis"
  type        = bool
  default     = false
}

variable "lambda_package_path" {
  description = "Path to Lambda deployment packages"
  type        = string
  default     = "./lambda_packages"
}
