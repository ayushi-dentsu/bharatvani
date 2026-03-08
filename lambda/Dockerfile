FROM --platform=linux/amd64 public.ecr.aws/lambda/python:3.12

# Install Python dependencies for Bedrock Nova Sonic streaming
RUN pip install --no-cache-dir \
    boto3 \
    aws-sdk-bedrock-runtime \
    smithy-aws-core

# Copy Lambda function code
COPY lambda_function.py ${LAMBDA_TASK_ROOT}/

CMD ["lambda_function.handler"]
