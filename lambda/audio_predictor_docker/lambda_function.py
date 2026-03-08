import json
import boto3
import librosa
import numpy as np
import joblib
import os

s3 = boto3.client("s3")

MODEL_BUCKET = "respiratory-ml-models"
MODEL_KEY = "models/cough_model2.pkl"

MODEL_PATH = "/tmp/cough_model2.pkl"

# download model once
if not os.path.exists(MODEL_PATH):
    s3.download_file(MODEL_BUCKET, MODEL_KEY, MODEL_PATH)

model = joblib.load(MODEL_PATH)


def extract_features(file_path):

    audio, sample_rate = librosa.load(file_path, res_type='kaiser_fast')

    mfcc = librosa.feature.mfcc(y=audio, sr=sample_rate, n_mfcc=40)
    delta = librosa.feature.delta(mfcc)
    delta2 = librosa.feature.delta(mfcc, order=2)

    spectral_centroid = librosa.feature.spectral_centroid(y=audio, sr=sample_rate)
    spectral_bandwidth = librosa.feature.spectral_bandwidth(y=audio, sr=sample_rate)
    zcr = librosa.feature.zero_crossing_rate(audio)

    features = np.hstack([
        np.mean(mfcc.T, axis=0),
        np.mean(delta.T, axis=0),
        np.mean(delta2.T, axis=0),
        np.mean(spectral_centroid.T, axis=0),
        np.mean(spectral_bandwidth.T, axis=0),
        np.mean(zcr.T, axis=0)
    ])

    return features


def lambda_handler(event, context):

    bucket = event['Records'][0]['s3']['bucket']['name']
    key = event['Records'][0]['s3']['object']['key']

    # Extract screeningId from S3 key: health-intake/cough/{screeningId}.wav
    filename = key.split('/')[-1]
    screening_id = filename.replace('.wav', '')

    audio_path = "/tmp/audio.wav"

    # download uploaded audio
    s3.download_file(bucket, key, audio_path)

    # extract features
    features = extract_features(audio_path)
    features = features.reshape(1, -1)

    # prediction probability
    prob = model.predict_proba(features)[0][1]

    threshold = 0.25
    prediction = bool(prob > threshold)

    print(f"Screening {screening_id} — Prediction: {prediction}, Probability: {prob:.4f}")

    # Write result to DynamoDB
    dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
    table = dynamodb.Table(os.environ.get("SCREENING_TABLE", "bharatvani-screenings"))
    table.update_item(
        Key={"screeningId": screening_id},
        UpdateExpression="SET audio_result = :ar, audio_probability = :ap",
        ExpressionAttributeValues={
            ":ar": prediction,
            ":ap": str(round(prob, 4)),
        },
    )

    return {
        "screeningId": screening_id,
        "prediction": prediction,
        "probability": float(prob)
    }
