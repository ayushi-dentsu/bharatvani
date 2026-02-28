variable "aws_region" {
  description = "AWS region for deployment"
  type        = string
  default     = "ap-south-1"
}

variable "connect_region" {
  description = "AWS region for Amazon Connect (must be a supported region: us-east-1, us-west-2, ap-southeast-1, ap-southeast-2, ap-northeast-1, eu-central-1, eu-west-2)"
  type        = string
  default     = "ap-southeast-1" # Singapore - closest to India
}

variable "environment" {
  description = "Environment name (dev/demo/prod)"
  type        = string
  default     = "demo"
}

variable "project_name" {
  description = "Project name for resource tagging"
  type        = string
  default     = "bharatvani"
}

variable "lambda_package_path" {
  description = "Path to Lambda deployment packages"
  type        = string
  default     = "./lambda_packages"
}

variable "team_members" {
  description = "List of team member email addresses for IAM user creation"
  type        = list(string)
  default = [
    "Raghavkripasthaya999@gmail.com",
    "harshada.javeri@gmail.com"
  ]
}

variable "enable_sqs" {
  description = "Enable SQS queues for decoupled processing (recommended for production)"
  type        = bool
  default     = false
}

variable "enable_connect" {
  description = "Enable Amazon Connect IVR (requires non-AISPL AWS account)"
  type        = bool
  default     = false
}

variable "enable_nova_sonic" {
  description = "Enable Amazon Nova Sonic for AI-powered audio analysis via Bedrock"
  type        = bool
  default     = false
}
