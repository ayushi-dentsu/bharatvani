output "connect_instance_id" {
  description = "Amazon Connect instance ID"
  value       = aws_connect_instance.bharatvani.id
}

output "connect_phone_number" {
  description = "Phone number for users to call"
  value       = aws_connect_phone_number.bharatvani.phone_number
}

output "instance_arn" {
  description = "Amazon Connect instance ARN"
  value       = aws_connect_instance.bharatvani.arn
}
