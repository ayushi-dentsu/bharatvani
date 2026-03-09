import json
import os
import boto3
import uuid
from datetime import datetime, timezone
from decimal import Decimal

bedrock = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION", "us-east-1"))
dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
lambda_client = boto3.client("lambda", region_name=os.environ.get("AWS_REGION", "us-east-1"))

TABLE_NAME = os.environ.get("SCREENING_TABLE", "bharatvani-screenings")
MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")


def _build_prompt(intake: dict, cough_result: dict, audio_result: dict) -> str:
    """Build prompt for Bedrock to aggregate and decorate the three screening outputs."""
    return f"""You are an aggregator for BharatVani, a rural health screening system in India.
You receive outputs from three separate screening sources. Your job is to combine them into a single,
decorated report that the patient sees on their dashboard. Use simple, reassuring language they can understand.
Do NOT perform your own medical analysis — just synthesize and present the existing results clearly.

## Patient Intake Data (Voice Conversation)
- Name: {intake.get('name', 'Unknown')}
- Age: {intake.get('age', 'Unknown')}
- Gender: {intake.get('gender', 'Unknown')}
- Symptoms: Fever={intake.get('fever', 0)}, Cold={intake.get('cold', 0)}, Cough={intake.get('cough', 0)}, Fatigue={intake.get('fatigue', 0)}, Loss of Smell={intake.get('loss_of_smell', 0)}, Breathing Difficulties={intake.get('breathing_difficulties', 0)}
- Medical History: Asthma={intake.get('asthma', 0)}, Diabetes={intake.get('diabetes', 0)}, Hypertension={intake.get('hypertension', 0)}, Smoker={intake.get('smoker', 0)}
(1 = Yes, 0 = No)

## Cough Predictor ML Model Output
- COVID Prediction: {"Positive" if cough_result.get('prediction', 0) == 1 else "Negative"}
- Model Confidence: {cough_result.get('confidence', 0):.1%}

## Audio Processing Analysis Output
- COVID Likelihood Score: {audio_result.get('covid_score', 'N/A')}
- Risk Classification: {audio_result.get('risk_label', 'N/A')}
- Analysis Confidence: {audio_result.get('confidence', 'N/A')}

Respond ONLY with valid JSON (no markdown, no extra text):
{{
  "riskLevel": "HIGH" or "MEDIUM" or "LOW",
  "riskScore": <number 0-100>,
  "confidence": <number 0-100>,
  "summary": "<2-3 sentence summary in simple language the patient can easily understand>",
  "keyFindings": ["<finding1>", "<finding2>", "<finding3>"],
  "recommendations": ["<simple action the user can take>", "<action2>", "<action3>"],
  "symptomBreakdown": {{
    "respiratoryRisk": "HIGH" or "MEDIUM" or "LOW",
    "covidIndicatorRisk": "HIGH" or "MEDIUM" or "LOW",
    "comorbidityRisk": "HIGH" or "MEDIUM" or "LOW"
  }},
  "urgency": "IMMEDIATE" or "SOON" or "ROUTINE",
  "followUpDays": <number 1-30>,
  "referralNeeded": true or false
}}"""


def _call_bedrock(prompt: str) -> dict:
    """Invoke Bedrock Nova Lite to aggregate and decorate the screening outputs."""
    response = bedrock.invoke_model(
        modelId=MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=json.dumps({
            "messages": [{"role": "user", "content": [{"text": prompt}]}],
            "inferenceConfig": {"maxTokens": 1024, "temperature": 0.2},
        }),
    )
    body = json.loads(response["body"].read())
    text = body["output"]["message"]["content"][0]["text"]
    # Strip markdown code fences if present
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    return json.loads(text)


def _get_screening(screening_id: str) -> dict:
    """Fetch the screening record from DynamoDB."""
    table = dynamodb.Table(TABLE_NAME)
    resp = table.get_item(Key={"screeningId": screening_id})
    return resp.get("Item", {})


def _is_pipeline_complete(record: dict) -> bool:
    """Check if all three pipeline stages have written their results."""
    return all(k in record for k in ("ecs_output", "cough_result", "audio_result"))


def _convert_floats(obj):
    """Recursively convert floats to Decimal for DynamoDB compatibility."""
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _convert_floats(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_convert_floats(i) for i in obj]
    return obj


def _save_assessment(screening_id: str, intake: dict, assessment: dict) -> None:
    """Write the final aggregated report back to DynamoDB."""
    table = dynamodb.Table(TABLE_NAME)
    table.update_item(
        Key={"screeningId": screening_id},
        UpdateExpression="SET assessment = :a, riskLevel = :r, riskScore = :s, "
                         "confidence = :c, summary = :sum, urgency = :u, "
                         "patientName = :n, aggregatedAt = :t",
        ExpressionAttributeValues={
            ":a": _convert_floats(assessment),
            ":r": assessment["riskLevel"],
            ":s": Decimal(str(assessment["riskScore"])),
            ":c": Decimal(str(assessment["confidence"])),
            ":sum": assessment["summary"],
            ":u": assessment["urgency"],
            ":n": intake.get("name", "Unknown"),
            ":t": datetime.now(timezone.utc).isoformat(),
        },
    )


def lambda_handler(event, context):
    """
    Screening Aggregator & Decorator.

    Triggered by DynamoDB Streams or direct invocation once all pipeline
    stages are complete. Pulls the three outputs from DynamoDB, calls
    Bedrock to produce a decorated report, and writes it back.

    Pipeline:
      1. ECS (IVR) → writes ecs_output to DynamoDB
      2. Cough Predictor Lambda → writes cough_result to DynamoDB
      3. Audio Processor Lambda → writes audio_result to DynamoDB
      4. This function → reads all three, aggregates via Bedrock, writes assessment

    Can be triggered via:
      - DynamoDB Stream (each upstream write triggers check for completeness)
      - Direct invocation with { "screeningId": "..." }
    """
    # Handle DynamoDB Stream events
    if "Records" in event:
        for record in event["Records"]:
            if record.get("eventName") in ("INSERT", "MODIFY"):
                new_image = record["dynamodb"].get("NewImage", {})
                screening_id = new_image.get("screeningId", {}).get("S", "")
                if screening_id:
                    _process_screening(screening_id)
        return {"statusCode": 200, "body": "Processed stream events"}

    # Handle direct invocation
    body = json.loads(event.get("body", "{}")) if isinstance(event.get("body"), str) else event
    screening_id = body.get("screeningId")

    if not screening_id:
        return {"statusCode": 400, "body": json.dumps({"error": "screeningId required"})}

    result = _process_screening(screening_id)
    if not result:
        return {
            "statusCode": 202,
            "body": json.dumps({"message": "Pipeline not yet complete", "screeningId": screening_id}),
        }

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps({
            "screeningId": screening_id,
            "assessment": result,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }),
    }


def _process_screening(screening_id: str) -> dict | None:
    """Check if all three inputs are ready, aggregate if so. Returns assessment or None."""
    record = _get_screening(screening_id)

    if not _is_pipeline_complete(record):
        return None

    # Parse the three inputs
    ecs_raw = record["ecs_output"]
    intake = json.loads(ecs_raw["body"]) if isinstance(ecs_raw.get("body"), str) else ecs_raw

    # cough_result and audio_result are booleans in DynamoDB — wrap them into
    # the dict format that _build_prompt expects
    cough_result = {
        "prediction": 1 if record["cough_result"] else 0,
        "confidence": float(record.get("cough_confidence", 0)),
    }
    audio_result = {
        "covid_score": float(record.get("audio_probability", 0)),
        "risk_label": "Positive" if record["audio_result"] else "Negative",
        "confidence": float(record.get("audio_probability", 0)),
    }

    # Aggregate via Bedrock
    prompt = _build_prompt(intake, cough_result, audio_result)
    assessment = _call_bedrock(prompt)

    # Persist
    _save_assessment(screening_id, intake, assessment)

    return assessment
