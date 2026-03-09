import json
import os
import boto3
from decimal import Decimal

dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
TABLE_NAME = os.environ.get("SCREENING_TABLE", "bharatvani-screenings")


class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return float(o)
        return super().default(o)


def lambda_handler(event, context):
    # Parse screeningId from query string or body
    screening_id = None
    qs = event.get("queryStringParameters") or {}
    screening_id = qs.get("screeningId") or qs.get("id")

    if not screening_id:
        body = event.get("body", "{}")
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except:
                body = {}
        screening_id = body.get("screeningId") or body.get("id")

    if not screening_id:
        return {
            "statusCode": 400,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"error": "screeningId required (query param or body)"}),
        }

    table = dynamodb.Table(TABLE_NAME)
    resp = table.get_item(Key={"screeningId": screening_id})
    item = resp.get("Item")

    if not item:
        return {
            "statusCode": 404,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"error": "Screening not found"}),
        }

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps(item, cls=DecimalEncoder),
    }
