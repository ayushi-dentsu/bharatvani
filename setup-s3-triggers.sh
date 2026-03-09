#!/bin/bash
# Setup S3 triggers for both Lambda functions on the IVR recordings bucket.
# Run this ONCE, or whenever triggers need to be reconfigured.
set -euo pipefail
export AWS_PAGER=""

BUCKET="ivr-call-recordings-797882812707-us-east-1"
REGION="us-east-1"
ACCOUNT_ID="797882812707"

AUDIO_PREDICTOR_ARN="arn:aws:lambda:${REGION}:${ACCOUNT_ID}:function:bharatvani-audio-predictor"
COUGH_PREDICTOR_ARN="arn:aws:lambda:${REGION}:${ACCOUNT_ID}:function:cough-predictor"

echo "==> Granting S3 invoke permissions..."
aws lambda add-permission \
  --function-name bharatvani-audio-predictor \
  --statement-id s3-wav-trigger \
  --action lambda:InvokeFunction \
  --principal s3.amazonaws.com \
  --source-arn "arn:aws:s3:::${BUCKET}" \
  --region "${REGION}" 2>/dev/null || true

aws lambda add-permission \
  --function-name cough-predictor \
  --statement-id s3-json-trigger \
  --action lambda:InvokeFunction \
  --principal s3.amazonaws.com \
  --source-arn "arn:aws:s3:::${BUCKET}" \
  --region "${REGION}" 2>/dev/null || true

echo "==> Setting S3 notification configuration (both triggers)..."
aws s3api put-bucket-notification-configuration \
  --bucket "${BUCKET}" \
  --notification-configuration "{
    \"LambdaFunctionConfigurations\": [
      {
        \"LambdaFunctionArn\": \"${AUDIO_PREDICTOR_ARN}\",
        \"Events\": [\"s3:ObjectCreated:*\"],
        \"Filter\": {\"Key\": {\"FilterRules\": [{\"Name\": \"prefix\", \"Value\": \"health-intake/cough/\"}, {\"Name\": \"suffix\", \"Value\": \".wav\"}]}}
      },
      {
        \"LambdaFunctionArn\": \"${COUGH_PREDICTOR_ARN}\",
        \"Events\": [\"s3:ObjectCreated:*\"],
        \"Filter\": {\"Key\": {\"FilterRules\": [{\"Name\": \"prefix\", \"Value\": \"health-intake/json/\"}, {\"Name\": \"suffix\", \"Value\": \".json\"}]}}
      }
    ]
  }" \
  --region "${REGION}"

echo "==> Done. Both triggers configured:"
echo "    .wav -> bharatvani-audio-predictor"
echo "    .json -> cough-predictor"
