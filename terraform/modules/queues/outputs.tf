output "audio_processing_queue_url" {
  description = "URL of the audio processing queue"
  value       = aws_sqs_queue.audio_processing.url
}

output "audio_processing_queue_arn" {
  description = "ARN of the audio processing queue"
  value       = aws_sqs_queue.audio_processing.arn
}

output "audio_processing_dlq_url" {
  description = "URL of the audio processing dead-letter queue"
  value       = aws_sqs_queue.audio_processing_dlq.url
}

output "ml_results_queue_url" {
  description = "URL of the ML results queue"
  value       = aws_sqs_queue.ml_results.url
}

output "ml_results_queue_arn" {
  description = "ARN of the ML results queue"
  value       = aws_sqs_queue.ml_results.arn
}

output "ml_results_dlq_url" {
  description = "URL of the ML results dead-letter queue"
  value       = aws_sqs_queue.ml_results_dlq.url
}
