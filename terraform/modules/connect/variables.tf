variable "environment" {
  description = "Environment name (dev/demo/prod)"
  type        = string
}

variable "project_name" {
  description = "Project name for resource tagging"
  type        = string
}

variable "audio_bucket_id" {
  description = "S3 bucket ID for audio storage"
  type        = string
}

variable "audio_bucket_arn" {
  description = "S3 bucket ARN for audio storage"
  type        = string
}

variable "connect_region" {
  description = "AWS region for Amazon Connect (must be a supported region)"
  type        = string
  default     = "ap-southeast-1" # Singapore - closest to India
}
