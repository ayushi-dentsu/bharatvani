variable "environment" {
  description = "Environment name (dev/demo/prod)"
  type        = string
}

variable "project_name" {
  description = "Project name for resource tagging"
  type        = string
}

variable "ml_classifier_lambda_arn" {
  description = "ARN of the ML classifier Lambda function"
  type        = string
}

variable "sms_handler_lambda_arn" {
  description = "ARN of the SMS handler Lambda function"
  type        = string
}
