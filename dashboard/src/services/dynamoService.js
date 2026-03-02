import { ScanCommand, QueryCommand, GetCommand } from '@aws-sdk/lib-dynamodb';
import { docClient, config } from '../config/aws';

export const getRecentScreenings = async (limit = 50) => {
  const command = new ScanCommand({
    TableName: config.dynamoTable,
    Limit: limit
  });

  const response = await docClient.send(command);
  return response.Items || [];
};

export const getScreeningById = async (id) => {
  const command = new GetCommand({
    TableName: config.dynamoTable,
    Key: { screeningId: id }
  });

  const response = await docClient.send(command);
  return response.Item;
};

export const getScreeningStats = async () => {
  const screenings = await getRecentScreenings(1000);
  
  const highRisk = screenings.filter(s => s.riskLevel === 'HIGH').length;
  const lowRisk = screenings.filter(s => s.riskLevel === 'LOW').length;
  
  return {
    total: screenings.length,
    highRisk,
    lowRisk,
    avgConfidence: (screenings.reduce((sum, s) => sum + (s.confidence || 0), 0) / screenings.length).toFixed(2)
  };
};
