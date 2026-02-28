resource "aws_sns_topic" "sms_notifications" {
  name = "${var.project_name}-sms-${var.environment}"

  tags = {
    Name        = "${var.project_name}-sms-${var.environment}"
    Environment = var.environment
    Project     = var.project_name
  }
}

# SNS SMS Preferences
# Note: MonthlySpendLimit defaults to $1 USD for new AWS accounts
# To increase the limit, submit a support request to AWS
# For hackathon demo, the default $1 limit should be sufficient (~100 SMS messages)
resource "aws_sns_sms_preferences" "sms_config" {
  monthly_spend_limit = "1"  # $1 USD (default for most accounts)
  default_sms_type    = "Transactional"
}
