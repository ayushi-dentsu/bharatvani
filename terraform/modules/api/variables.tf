variable "environment" {
  description = "Environment name (dev/demo/prod)"
  type        = string
}

variable "project_name" {
  description = "Project name for resource tagging"
  type        = string
}

variable "upload_url_lambda_invoke_arn" {
  description = "Invoke ARN of the upload URL Lambda function"
  type        = string
}

variable "upload_url_lambda_name" {
  description = "Name of the upload URL Lambda function"
  type        = string
}

variable "results_lambda_invoke_arn" {
  description = "Invoke ARN of the results Lambda function"
  type        = string
}

variable "results_lambda_name" {
  description = "Name of the results Lambda function"
  type        = string
}
