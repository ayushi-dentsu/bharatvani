import json
import boto3
import os
from decimal import Decimal

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['DYNAMODB_TABLE'])

class DecimalEncoder(json.JSONEncoder):
    """Helper class to convert DynamoDB Decimal to JSON"""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

def lambda_handler(event, context):
    """
    Get processing results from DynamoDB for a recording ID
    React app polls this endpoint to check if results are ready
    """
    try:
        # Get recording ID from path parameters
        recording_id = event['pathParameters']['recordingId']
        
        # Query DynamoDB for results
        # Note: You'll need to adjust this based on your actual DynamoDB schema
        # This assumes you're storing results with recording_id as a key
        
        response = table.query(
            IndexName='recording-id-index',  # You'll need to create this GSI
            KeyConditionExpression='recording_id = :rid',
            ExpressionAttributeValues={
                ':rid': recording_id
            }
        )
        
        if response['Items']:
            result = response['Items'][0]
            
            return {
                'statusCode': 200,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Content-Type',
                    'Content-Type': 'application/json'
                },
                'body': json.dumps({
                    'status': 'completed',
                    'recordingId': recording_id,
                    'riskLevel': result.get('risk_level', 'unknown'),
                    'confidence': result.get('confidence_score', 0),
                    'features': result.get('features', {}),
                    'timestamp': result.get('screening_timestamp', ''),
                    'smsStatus': result.get('sms_status', 'sent')
                }, cls=DecimalEncoder)
            }
        else:
            # Results not ready yet
            return {
                'statusCode': 200,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Content-Type': 'application/json'
                },
                'body': json.dumps({
                    'status': 'processing',
                    'recordingId': recording_id,
                    'message': 'Results not ready yet. Please try again in a few seconds.'
                })
            }
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Content-Type': 'application/json'
            },
            'body': json.dumps({
                'error': 'Failed to fetch results',
                'message': str(e)
            })
        }
