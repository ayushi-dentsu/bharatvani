# Use AWS Lambda Python base image
FROM public.ecr.aws/lambda/python:3.12

# Copy the lambda function code
COPY cough-predictor/lambda_function.py ${LAMBDA_TASK_ROOT}/

# Install required Python packages for Linux
# boto3 is already included in Lambda base image
RUN pip install --no-cache-dir \
    numpy \
    scikit-learn \
    xgboost \
    joblib && \
    pip list

# Set the CMD to your handler
CMD [ "lambda_function.lambda_handler" ]
