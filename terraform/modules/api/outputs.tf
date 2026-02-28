output "api_gateway_url" {
  description = "API Gateway invoke URL (use this in your React app)"
  value       = aws_api_gateway_stage.bharatvani.invoke_url
}

output "api_gateway_id" {
  description = "API Gateway REST API ID"
  value       = aws_api_gateway_rest_api.bharatvani.id
}

output "api_gateway_stage_name" {
  description = "API Gateway stage name"
  value       = aws_api_gateway_stage.bharatvani.stage_name
}
