output "audio_processor_arn" {
  description = "ARN of the Audio Processor Lambda function"
  value       = aws_lambda_function.audio_processor.arn
}

output "audio_processor_name" {
  description = "Name of the Audio Processor Lambda function"
  value       = aws_lambda_function.audio_processor.function_name
}

output "ml_classifier_arn" {
  description = "ARN of the ML Classifier Lambda function"
  value       = aws_lambda_function.ml_classifier.arn
}

output "ml_classifier_name" {
  description = "Name of the ML Classifier Lambda function"
  value       = aws_lambda_function.ml_classifier.function_name
}

output "sms_handler_arn" {
  description = "ARN of the SMS Handler Lambda function"
  value       = aws_lambda_function.sms_handler.arn
}

output "sms_handler_name" {
  description = "Name of the SMS Handler Lambda function"
  value       = aws_lambda_function.sms_handler.function_name
}

output "nova_sonic_analyzer_arn" {
  description = "ARN of the Nova Sonic Analyzer Lambda function (if enabled)"
  value       = var.enable_nova_sonic ? aws_lambda_function.nova_sonic_analyzer[0].arn : null
}

output "nova_sonic_analyzer_name" {
  description = "Name of the Nova Sonic Analyzer Lambda function (if enabled)"
  value       = var.enable_nova_sonic ? aws_lambda_function.nova_sonic_analyzer[0].function_name : null
}

output "lambda_role_arn" {
  description = "ARN of the Lambda execution IAM role"
  value       = aws_iam_role.lambda_exec.arn
}
