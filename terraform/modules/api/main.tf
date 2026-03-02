# API Gateway REST API
resource "aws_api_gateway_rest_api" "bharatvani" {
  name        = "${var.project_name}-api-${var.environment}"
  description = "BharatVani API for frontend integration"

  endpoint_configuration {
    types = ["REGIONAL"]
  }

  tags = {
    Name        = "${var.project_name}-api-${var.environment}"
    Environment = var.environment
    Project     = var.project_name
  }
}

# CORS configuration
resource "aws_api_gateway_gateway_response" "cors" {
  rest_api_id   = aws_api_gateway_rest_api.bharatvani.id
  response_type = "DEFAULT_4XX"

  response_parameters = {
    "gatewayresponse.header.Access-Control-Allow-Origin"  = "'*'"
    "gatewayresponse.header.Access-Control-Allow-Headers" = "'*'"
  }
}

# /upload-url endpoint - Get pre-signed URL for S3 upload
resource "aws_api_gateway_resource" "upload_url" {
  rest_api_id = aws_api_gateway_rest_api.bharatvani.id
  parent_id   = aws_api_gateway_rest_api.bharatvani.root_resource_id
  path_part   = "upload-url"
}

resource "aws_api_gateway_method" "upload_url_post" {
  rest_api_id   = aws_api_gateway_rest_api.bharatvani.id
  resource_id   = aws_api_gateway_resource.upload_url.id
  http_method   = "POST"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "upload_url_lambda" {
  rest_api_id             = aws_api_gateway_rest_api.bharatvani.id
  resource_id             = aws_api_gateway_resource.upload_url.id
  http_method             = aws_api_gateway_method.upload_url_post.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = var.upload_url_lambda_invoke_arn
}

# /results/{recordingId} endpoint - Get processing results
resource "aws_api_gateway_resource" "results" {
  rest_api_id = aws_api_gateway_rest_api.bharatvani.id
  parent_id   = aws_api_gateway_rest_api.bharatvani.root_resource_id
  path_part   = "results"
}

resource "aws_api_gateway_resource" "results_id" {
  rest_api_id = aws_api_gateway_rest_api.bharatvani.id
  parent_id   = aws_api_gateway_resource.results.id
  path_part   = "{recordingId}"
}

resource "aws_api_gateway_method" "results_get" {
  rest_api_id   = aws_api_gateway_rest_api.bharatvani.id
  resource_id   = aws_api_gateway_resource.results_id.id
  http_method   = "GET"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "results_lambda" {
  rest_api_id             = aws_api_gateway_rest_api.bharatvani.id
  resource_id             = aws_api_gateway_resource.results_id.id
  http_method             = aws_api_gateway_method.results_get.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = var.results_lambda_invoke_arn
}

# CORS for upload-url
resource "aws_api_gateway_method" "upload_url_options" {
  rest_api_id   = aws_api_gateway_rest_api.bharatvani.id
  resource_id   = aws_api_gateway_resource.upload_url.id
  http_method   = "OPTIONS"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "upload_url_options" {
  rest_api_id = aws_api_gateway_rest_api.bharatvani.id
  resource_id = aws_api_gateway_resource.upload_url.id
  http_method = aws_api_gateway_method.upload_url_options.http_method
  type        = "MOCK"

  request_templates = {
    "application/json" = "{\"statusCode\": 200}"
  }
}

resource "aws_api_gateway_method_response" "upload_url_options" {
  rest_api_id = aws_api_gateway_rest_api.bharatvani.id
  resource_id = aws_api_gateway_resource.upload_url.id
  http_method = aws_api_gateway_method.upload_url_options.http_method
  status_code = "200"

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = true
    "method.response.header.Access-Control-Allow-Methods" = true
    "method.response.header.Access-Control-Allow-Origin"  = true
  }
}

resource "aws_api_gateway_integration_response" "upload_url_options" {
  rest_api_id = aws_api_gateway_rest_api.bharatvani.id
  resource_id = aws_api_gateway_resource.upload_url.id
  http_method = aws_api_gateway_method.upload_url_options.http_method
  status_code = aws_api_gateway_method_response.upload_url_options.status_code

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = "'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'"
    "method.response.header.Access-Control-Allow-Methods" = "'POST,OPTIONS'"
    "method.response.header.Access-Control-Allow-Origin"  = "'*'"
  }
}

# CORS for results
resource "aws_api_gateway_method" "results_options" {
  rest_api_id   = aws_api_gateway_rest_api.bharatvani.id
  resource_id   = aws_api_gateway_resource.results_id.id
  http_method   = "OPTIONS"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "results_options" {
  rest_api_id = aws_api_gateway_rest_api.bharatvani.id
  resource_id = aws_api_gateway_resource.results_id.id
  http_method = aws_api_gateway_method.results_options.http_method
  type        = "MOCK"

  request_templates = {
    "application/json" = "{\"statusCode\": 200}"
  }
}

resource "aws_api_gateway_method_response" "results_options" {
  rest_api_id = aws_api_gateway_rest_api.bharatvani.id
  resource_id = aws_api_gateway_resource.results_id.id
  http_method = aws_api_gateway_method.results_options.http_method
  status_code = "200"

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = true
    "method.response.header.Access-Control-Allow-Methods" = true
    "method.response.header.Access-Control-Allow-Origin"  = true
  }
}

resource "aws_api_gateway_integration_response" "results_options" {
  rest_api_id = aws_api_gateway_rest_api.bharatvani.id
  resource_id = aws_api_gateway_resource.results_id.id
  http_method = aws_api_gateway_method.results_options.http_method
  status_code = aws_api_gateway_method_response.results_options.status_code

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = "'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'"
    "method.response.header.Access-Control-Allow-Methods" = "'GET,OPTIONS'"
    "method.response.header.Access-Control-Allow-Origin"  = "'*'"
  }
}

# API Gateway Deployment
resource "aws_api_gateway_deployment" "bharatvani" {
  rest_api_id = aws_api_gateway_rest_api.bharatvani.id

  depends_on = [
    aws_api_gateway_integration.upload_url_lambda,
    aws_api_gateway_integration.results_lambda,
    aws_api_gateway_integration.upload_url_options,
    aws_api_gateway_integration.results_options
  ]

  lifecycle {
    create_before_destroy = true
  }
}

# API Gateway Stage
resource "aws_api_gateway_stage" "bharatvani" {
  deployment_id = aws_api_gateway_deployment.bharatvani.id
  rest_api_id   = aws_api_gateway_rest_api.bharatvani.id
  stage_name    = var.environment

  tags = {
    Name        = "${var.project_name}-api-${var.environment}"
    Environment = var.environment
    Project     = var.project_name
  }
}

# Lambda permissions for API Gateway
resource "aws_lambda_permission" "upload_url_api" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = var.upload_url_lambda_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.bharatvani.execution_arn}/*/*"
}

resource "aws_lambda_permission" "results_api" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = var.results_lambda_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.bharatvani.execution_arn}/*/*"
}
