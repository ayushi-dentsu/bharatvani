import { InvokeCommand } from '@aws-sdk/client-lambda';
import { lambdaClient, config } from '../config/aws';

export const invokeMlAnalysis = async (audioKey) => {
  const payload = {
    audioKey,
    bucket: config.s3Bucket
  };

  const command = new InvokeCommand({
    FunctionName: config.lambdaFunction,
    Payload: JSON.stringify(payload)
  });

  const response = await lambdaClient.send(command);
  const result = JSON.parse(new TextDecoder().decode(response.Payload));
  return result;
};

export const getLambdaMetrics = async () => {
  // Returns mock data - integrate with CloudWatch for real metrics
  return {
    invocations: 1250,
    avgDuration: 2.3,
    errorRate: 0.02
  };
};
