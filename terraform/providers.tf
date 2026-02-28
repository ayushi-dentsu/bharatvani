terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }
}

# Default provider for most resources (Mumbai region)
provider "aws" {
  region = var.aws_region
}

# Separate provider for Amazon Connect (Singapore region)
# Amazon Connect is not available in ap-south-1 (Mumbai)
provider "aws" {
  alias  = "connect"
  region = var.connect_region
}
