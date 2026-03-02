output "sns_topic_arn" {
  description = "ARN of the SNS topic for SMS notifications"
  value       = aws_sns_topic.sms_notifications.arn
}
