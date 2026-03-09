import json
import joblib
import boto3
import numpy as np
import os

s3 = boto3.client("s3")

BUCKET = "respiratory-ml-models"

MODEL_PATH = "/tmp/model.pkl"
SCALER_PATH = "/tmp/scaler.pkl"
ENCODER_PATH = "/tmp/encoder.pkl"


def download_file(key, path):
    if not os.path.exists(path):
        s3.download_file(BUCKET, key, path)


def load_models():
    download_file("covid_model2.pkl", MODEL_PATH)
    download_file("scaler2.pkl", SCALER_PATH)
    download_file("gender_encoder2.pkl", ENCODER_PATH)

    model = joblib.load(MODEL_PATH)
    scaler = joblib.load(SCALER_PATH)
    encoder = joblib.load(ENCODER_PATH)

    return model, scaler, encoder


model, scaler, encoder = load_models()


def lambda_handler(event, context):

    # Support both S3 trigger and direct invocation
    if "Records" in event:
        # Triggered by S3 .json upload
        bucket = event["Records"][0]["s3"]["bucket"]["name"]
        key = event["Records"][0]["s3"]["object"]["key"]
        screening_id = key.split("/")[-1].replace(".json", "")

        obj = s3.get_object(Bucket=bucket, Key=key)
        raw = json.loads(obj["Body"].read().decode("utf-8"))
        body = json.loads(raw["body"]) if isinstance(raw.get("body"), str) else raw
    else:
        body = json.loads(event["body"]) if isinstance(event.get("body"), str) else event
        screening_id = body.get("screeningId", "")

    # Map unknown gender codes to a safe default the encoder recognizes
    gender = body["gender"]
    if gender not in ("M", "F"):
        gender = "M"
    gender_encoded = encoder.transform([gender])[0]

    data = np.array([[
        body["age"],
        gender_encoded,
        body["fever"],
        body["cold"],
        body["cough"],
        body["fatigue"],
        body["loss_of_smell"],
        body["breathing_difficulties"],
        body["asthma"],
        body["diabetes"],
        body["hypertension"],
        body["smoker"]
    ]])

    data_scaled = scaler.transform(data)

    prediction = model.predict(data_scaled)[0]
    probability = model.predict_proba(data_scaled)[0][1]

    result = bool(int(prediction) == 1)

    print(f"Screening {screening_id} — Prediction: {result}, Confidence: {probability:.4f}")

    # Write result to DynamoDB
    if screening_id:
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        table = dynamodb.Table(os.environ.get("SCREENING_TABLE", "bharatvani-screenings"))
        table.update_item(
            Key={"screeningId": screening_id},
            UpdateExpression="SET cough_result = :cr, cough_confidence = :cc",
            ExpressionAttributeValues={
                ":cr": result,
                ":cc": str(round(float(probability), 4)),
            },
        )

    return {
        "statusCode": 200,
        "body": json.dumps({
            "screeningId": screening_id,
            "prediction": int(prediction),
            "confidence": float(probability)
        })
    }
