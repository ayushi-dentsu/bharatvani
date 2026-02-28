import json
import boto3
import os
from datetime import datetime
import uuid

s3_client = boto3.client('s3')
BUCKET_NAME = os.environ['AUDIO_BUCKET']

def lambda_handler(event, context):
    """
    Generate pre-signed URL for React app to upload audio to S3
    """
    try:
        # Parse request body
        body = json.loads(event['body'])
        phone_number = body.get('phoneNumber', 'unknown')
        
        # Generate unique recording ID
        recording_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()
        filename = f"recordings/{recording_id}.wav"
        
        # Generate pre-signed URL for upload (5 minutes expiry)
        presigned_url = s3_client.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': BUCKET_NAME,
                'Key': filename,
                'ContentType': 'audio/wav',
                'Metadata': {
                    'phone_number': phone_number,
                    'timestamp': timestamp,
                    'recording_id': recording_id
                }
            },
            ExpiresIn=300
        )
        
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Content-Type': 'application/json'
            },
            'body': json.dumps({
                'uploadUrl': presigned_url,
                'recordingId': recording_id,
                'message': 'Upload URL generated successfully'
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
                'error': 'Failed to generate upload URL',
                'message': str(e)
            })
        }
