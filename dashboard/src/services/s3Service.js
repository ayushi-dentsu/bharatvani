import { GetObjectCommand, ListObjectsV2Command } from '@aws-sdk/client-s3';
import { getSignedUrl } from '@aws-sdk/s3-request-presigner';
import { s3Client, config } from '../config/aws';

export const listAudioFiles = async (prefix = '') => {
  const command = new ListObjectsV2Command({
    Bucket: config.s3Bucket,
    Prefix: prefix,
    MaxKeys: 100
  });
  
  const response = await s3Client.send(command);
  return response.Contents || [];
};

export const getAudioUrl = async (key) => {
  const command = new GetObjectCommand({
    Bucket: config.s3Bucket,
    Key: key
  });
  
  return await getSignedUrl(s3Client, command, { expiresIn: 3600 });
};

export const getAudioMetadata = async (key) => {
  const command = new GetObjectCommand({
    Bucket: config.s3Bucket,
    Key: key
  });
  
  const response = await s3Client.send(command);
  return response.Metadata;
};
