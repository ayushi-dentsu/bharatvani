# IAM Role for Lambda Execution
resource "aws_iam_role" "lambda_exec" {
  name = "${var.project_name}-lambda-exec-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })

  tags = {
    Name        = "${var.project_name}-lambda-exec-${var.environment}"
    Environment = var.environment
    Project     = var.project_name
  }
}

# IAM Policy for S3 Access
resource "aws_iam_role_policy" "lambda_s3_policy" {
  name = "${var.project_name}-lambda-s3-policy"
  role = aws_iam_role.lambda_exec.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject"
        ]
        Resource = [
          "arn:aws:s3:::${var.audio_bucket_name}/*",
          "arn:aws:s3:::${var.models_bucket_name}/*"
        ]
      }
    ]
  })
}

# IAM Policy for DynamoDB Access
resource "aws_iam_role_policy" "lambda_dynamodb_policy" {
  name = "${var.project_name}-lambda-dynamodb-policy"
  role = aws_iam_role.lambda_exec.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query"
        ]
        Resource = "arn:aws:dynamodb:*:*:table/${var.dynamodb_table_name}"
      }
    ]
  })
}

# IAM Policy for Lambda Invoke Permissions
resource "aws_iam_role_policy" "lambda_invoke_policy" {
  name = "${var.project_name}-lambda-invoke-policy"
  role = aws_iam_role.lambda_exec.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "lambda:InvokeFunction"
        ]
        Resource = [
          aws_lambda_function.ml_classifier.arn,
          aws_lambda_function.sms_handler.arn
        ]
      }
    ]
  })
}

# IAM Policy for SNS Publish
resource "aws_iam_role_policy" "lambda_sns_policy" {
  name = "${var.project_name}-lambda-sns-policy"
  role = aws_iam_role.lambda_exec.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "sns:Publish"
        ]
        Resource = var.sns_topic_arn
      }
    ]
  })
}

# IAM Policy for CloudWatch Logs
resource "aws_iam_role_policy" "lambda_logs_policy" {
  name = "${var.project_name}-lambda-logs-policy"
  role = aws_iam_role.lambda_exec.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}


# CloudWatch Log Group for Audio Processor
resource "aws_cloudwatch_log_group" "audio_processor" {
  name              = "/aws/lambda/${var.project_name}-audio-processor-${var.environment}"
  retention_in_days = 7

  tags = {
    Name        = "${var.project_name}-audio-processor-logs"
    Environment = var.environment
    Project     = var.project_name
  }
}

# Audio Processor Lambda Function
resource "aws_lambda_function" "audio_processor" {
  function_name = "${var.project_name}-audio-processor-${var.environment}"
  runtime       = "python3.9"
  handler       = "handler.process_audio"
  memory_size   = 1024
  timeout       = 30
  role          = aws_iam_role.lambda_exec.arn

  filename         = "${var.lambda_package_path}/audio_processor.zip"
  source_code_hash = filebase64sha256("${var.lambda_package_path}/audio_processor.zip")

  environment {
    variables = {
      AUDIO_BUCKET   = var.audio_bucket_name
      MODEL_BUCKET   = var.models_bucket_name
      DYNAMODB_TABLE = var.dynamodb_table_name
      ML_LAMBDA_ARN  = aws_lambda_function.ml_classifier.arn
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.audio_processor,
    aws_iam_role_policy.lambda_logs_policy
  ]

  tags = {
    Name        = "${var.project_name}-audio-processor"
    Environment = var.environment
    Project     = var.project_name
  }
}


# CloudWatch Log Group for ML Classifier
resource "aws_cloudwatch_log_group" "ml_classifier" {
  name              = "/aws/lambda/${var.project_name}-ml-classifier-${var.environment}"
  retention_in_days = 7

  tags = {
    Name        = "${var.project_name}-ml-classifier-logs"
    Environment = var.environment
    Project     = var.project_name
  }
}

# ML Classifier Lambda Function
resource "aws_lambda_function" "ml_classifier" {
  function_name = "${var.project_name}-ml-classifier-${var.environment}"
  runtime       = "python3.9"
  handler       = "handler.classify_health"
  memory_size   = 2048
  timeout       = 30
  role          = aws_iam_role.lambda_exec.arn

  filename         = "${var.lambda_package_path}/ml_classifier.zip"
  source_code_hash = filebase64sha256("${var.lambda_package_path}/ml_classifier.zip")

  environment {
    variables = {
      MODEL_BUCKET   = var.models_bucket_name
      MODEL_KEY      = "respiratory_model.pkl"
      DYNAMODB_TABLE = var.dynamodb_table_name
      SMS_LAMBDA_ARN = aws_lambda_function.sms_handler.arn
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.ml_classifier,
    aws_iam_role_policy.lambda_logs_policy
  ]

  tags = {
    Name        = "${var.project_name}-ml-classifier"
    Environment = var.environment
    Project     = var.project_name
  }
}


# CloudWatch Log Group for SMS Handler
resource "aws_cloudwatch_log_group" "sms_handler" {
  name              = "/aws/lambda/${var.project_name}-sms-handler-${var.environment}"
  retention_in_days = 7

  tags = {
    Name        = "${var.project_name}-sms-handler-logs"
    Environment = var.environment
    Project     = var.project_name
  }
}

# SMS Handler Lambda Function
resource "aws_lambda_function" "sms_handler" {
  function_name = "${var.project_name}-sms-handler-${var.environment}"
  runtime       = "python3.9"
  handler       = "handler.send_sms"
  memory_size   = 512
  timeout       = 10
  role          = aws_iam_role.lambda_exec.arn

  filename         = "${var.lambda_package_path}/sms_handler.zip"
  source_code_hash = filebase64sha256("${var.lambda_package_path}/sms_handler.zip")

  environment {
    variables = {
      SNS_TOPIC_ARN  = var.sns_topic_arn
      DYNAMODB_TABLE = var.dynamodb_table_name
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.sms_handler,
    aws_iam_role_policy.lambda_logs_policy
  ]

  tags = {
    Name        = "${var.project_name}-sms-handler"
    Environment = var.environment
    Project     = var.project_name
  }
}


# CloudWatch Log Group for Nova Sonic Analyzer (conditional)
resource "aws_cloudwatch_log_group" "nova_sonic_analyzer" {
  count             = var.enable_nova_sonic ? 1 : 0
  name              = "/aws/lambda/${var.project_name}-nova-sonic-${var.environment}"
  retention_in_days = 7

  tags = {
    Name        = "${var.project_name}-nova-sonic-logs"
    Environment = var.environment
    Project     = var.project_name
  }
}

# Nova Sonic Analyzer Lambda Function (conditional)
resource "aws_lambda_function" "nova_sonic_analyzer" {
  count         = var.enable_nova_sonic ? 1 : 0
  function_name = "${var.project_name}-nova-sonic-${var.environment}"
  runtime       = "python3.9"
  handler       = "handler.analyze_audio"
  memory_size   = 1024
  timeout       = 60
  role          = aws_iam_role.lambda_exec.arn

  filename         = "${var.lambda_package_path}/nova_sonic_analyzer.zip"
  source_code_hash = filebase64sha256("${var.lambda_package_path}/nova_sonic_analyzer.zip")

  environment {
    variables = {
      AUDIO_BUCKET     = var.audio_bucket_name
      DYNAMODB_TABLE   = var.dynamodb_table_name
      SMS_LAMBDA_ARN   = aws_lambda_function.sms_handler.arn
      BEDROCK_MODEL_ID = "amazon.nova-sonic-v1:0"
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.nova_sonic_analyzer,
    aws_iam_role_policy.lambda_logs_policy
  ]

  tags = {
    Name        = "${var.project_name}-nova-sonic-analyzer"
    Environment = var.environment
    Project     = var.project_name
  }
}


# IAM Policy for Bedrock Access (conditional)
resource "aws_iam_role_policy" "lambda_bedrock_policy" {
  count = var.enable_nova_sonic ? 1 : 0
  name  = "${var.project_name}-lambda-bedrock-policy"
  role  = aws_iam_role.lambda_exec.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream"
        ]
        Resource = "arn:aws:bedrock:*::foundation-model/amazon.nova-sonic-v1:0"
      }
    ]
  })
}
