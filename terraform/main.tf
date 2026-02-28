# IAM Module - Team member access
module "iam" {
  source = "./modules/iam"

  team_members = var.team_members
  environment  = var.environment
  project_name = var.project_name
}

# Storage Module - S3 buckets and DynamoDB
module "storage" {
  source = "./modules/storage"

  environment  = var.environment
  project_name = var.project_name
}

# Messaging Module - SNS for SMS
module "messaging" {
  source = "./modules/messaging"

  environment  = var.environment
  project_name = var.project_name
}

# Lambda Module - Serverless processing functions
module "lambda" {
  source = "./modules/lambda"

  environment         = var.environment
  project_name        = var.project_name
  lambda_package_path = var.lambda_package_path
  audio_bucket_name   = module.storage.audio_bucket_name
  models_bucket_name  = module.storage.models_bucket_name
  dynamodb_table_name = module.storage.dynamodb_table_name
  sns_topic_arn       = module.messaging.sns_topic_arn
  enable_nova_sonic   = var.enable_nova_sonic
}

# Connect Module - Amazon Connect IVR (optional, requires non-AISPL account)
module "connect" {
  count  = var.enable_connect ? 1 : 0
  source = "./modules/connect"
  providers = {
    aws.connect = aws.connect
  }

  environment      = var.environment
  project_name     = var.project_name
  audio_bucket_id  = module.storage.audio_bucket_name
  audio_bucket_arn = module.storage.audio_bucket_arn
}

# Frontend Module - React app hosting on S3 + CloudFront
module "frontend" {
  source = "./modules/frontend"

  environment  = var.environment
  project_name = var.project_name
}

# TODO: Queues Module - SQS queues (not yet implemented)
# module "queues" {
#   count  = var.enable_sqs ? 1 : 0
#   source = "./modules/queues"
#
#   environment              = var.environment
#   project_name             = var.project_name
#   ml_classifier_lambda_arn = module.lambda.ml_classifier_arn
#   sms_handler_lambda_arn   = module.lambda.sms_handler_arn
# }
