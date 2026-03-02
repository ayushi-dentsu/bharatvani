# Audio Processing Dead-Letter Queue
resource "aws_sqs_queue" "audio_processing_dlq" {
  name                      = "${var.project_name}-audio-processing-dlq-${var.environment}"
  message_retention_seconds = 1209600 # 14 days

  tags = {
    Name        = "${var.project_name} Audio Processing DLQ"
    Environment = var.environment
    Project     = var.project_name
  }
}

# Audio Processing Queue
resource "aws_sqs_queue" "audio_processing" {
  name                       = "${var.project_name}-audio-processing-${var.environment}"
  visibility_timeout_seconds = 180    # 3 minutes
  message_retention_seconds  = 345600 # 4 days
  receive_wait_time_seconds  = 20     # Long polling

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.audio_processing_dlq.arn
    maxReceiveCount     = 3
  })

  tags = {
    Name        = "${var.project_name} Audio Processing Queue"
    Environment = var.environment
    Project     = var.project_name
  }
}

# ML Results Dead-Letter Queue
resource "aws_sqs_queue" "ml_results_dlq" {
  name                      = "${var.project_name}-ml-results-dlq-${var.environment}"
  message_retention_seconds = 1209600 # 14 days

  tags = {
    Name        = "${var.project_name} ML Results DLQ"
    Environment = var.environment
    Project     = var.project_name
  }
}

# ML Results Queue
resource "aws_sqs_queue" "ml_results" {
  name                       = "${var.project_name}-ml-results-${var.environment}"
  visibility_timeout_seconds = 60     # 1 minute
  message_retention_seconds  = 345600 # 4 days
  receive_wait_time_seconds  = 20     # Long polling

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.ml_results_dlq.arn
    maxReceiveCount     = 3
  })

  tags = {
    Name        = "${var.project_name} ML Results Queue"
    Environment = var.environment
    Project     = var.project_name
  }
}

# Lambda Event Source Mapping - Audio Processing Queue to ML Classifier
resource "aws_lambda_event_source_mapping" "audio_processing" {
  event_source_arn = aws_sqs_queue.audio_processing.arn
  function_name    = var.ml_classifier_lambda_arn
  batch_size       = 1
  enabled          = true
}

# Lambda Event Source Mapping - ML Results Queue to SMS Handler
resource "aws_lambda_event_source_mapping" "ml_results" {
  event_source_arn = aws_sqs_queue.ml_results.arn
  function_name    = var.sms_handler_lambda_arn
  batch_size       = 1
  enabled          = true
}

# CloudWatch Alarm for Audio Processing DLQ
resource "aws_cloudwatch_metric_alarm" "audio_processing_dlq_alarm" {
  alarm_name          = "${var.project_name}-audio-processing-dlq-${var.environment}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300 # 5 minutes
  statistic           = "Average"
  threshold           = 0
  alarm_description   = "Alert when messages appear in audio processing DLQ"

  dimensions = {
    QueueName = aws_sqs_queue.audio_processing_dlq.name
  }

  tags = {
    Name        = "${var.project_name} Audio Processing DLQ Alarm"
    Environment = var.environment
    Project     = var.project_name
  }
}

# CloudWatch Alarm for ML Results DLQ
resource "aws_cloudwatch_metric_alarm" "ml_results_dlq_alarm" {
  alarm_name          = "${var.project_name}-ml-results-dlq-${var.environment}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300 # 5 minutes
  statistic           = "Average"
  threshold           = 0
  alarm_description   = "Alert when messages appear in ML results DLQ"

  dimensions = {
    QueueName = aws_sqs_queue.ml_results_dlq.name
  }

  tags = {
    Name        = "${var.project_name} ML Results DLQ Alarm"
    Environment = var.environment
    Project     = var.project_name
  }
}
