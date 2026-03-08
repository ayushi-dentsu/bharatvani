FROM --platform=linux/amd64 public.ecr.aws/lambda/python:3.12

# Install system deps for librosa (libsndfile)
RUN dnf install -y libsndfile && dnf clean all

# Install Python dependencies
RUN pip install --no-cache-dir \
    boto3 \
    librosa \
    numpy \
    joblib \
    scikit-learn \
    xgboost

# Separate layer to avoid re-pushing the big layer above
RUN pip install --no-cache-dir resampy

# Copy function code
COPY lambda_function.py ${LAMBDA_TASK_ROOT}/

CMD ["lambda_function.lambda_handler"]
