import { S3Client } from '@aws-sdk/client-s3';
import { LambdaClient } from '@aws-sdk/client-lambda';
import { DynamoDBClient } from '@aws-sdk/client-dynamodb';
import { DynamoDBDocumentClient } from '@aws-sdk/lib-dynamodb';

const AWS_REGION = process.env.REACT_APP_AWS_REGION || 'ap-south-1';

const credentials = {
  accessKeyId: process.env.REACT_APP_AWS_ACCESS_KEY_ID,
  secretAccessKey: process.env.REACT_APP_AWS_SECRET_ACCESS_KEY
};

export const s3Client = new S3Client({ 
  region: AWS_REGION,
  credentials 
});

export const lambdaClient = new LambdaClient({ 
  region: AWS_REGION,
  credentials 
});

const dynamoClient = new DynamoDBClient({ 
  region: AWS_REGION,
  credentials 
});

export const docClient = DynamoDBDocumentClient.from(dynamoClient);

export const config = {
  s3Bucket: process.env.REACT_APP_S3_BUCKET || 'bharatvani-audio',
  lambdaFunction: process.env.REACT_APP_LAMBDA_FUNCTION || 'bharatvani-ml-processor',
  dynamoTable: process.env.REACT_APP_DYNAMODB_TABLE || 'bharatvani-screenings'
};
