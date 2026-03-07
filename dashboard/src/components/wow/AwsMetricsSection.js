import React from 'react';
import { Activity, Database, HardDriveUpload, MessageSquareText, Zap } from 'lucide-react';
import { Line, LineChart, ResponsiveContainer } from 'recharts';
import SectionCard from './SectionCard';

const iconByMetric = {
  'Lambda Invocations': Zap,
  'Lambda Latency': Activity,
  'DynamoDB Writes': Database,
  'S3 Audio Uploads': HardDriveUpload,
  'SNS SMS Success Rate': MessageSquareText
};

export default function AwsMetricsSection({ awsMetrics }) {
  const list = Object.values(awsMetrics);

  return (
    <SectionCard title="Real-Time AWS Metrics" subtitle="CloudWatch-style service health" className="h-full">
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-5">
        {list.map((metric) => {
          const Icon = iconByMetric[metric.label] || Activity;

          return (
            <div key={metric.label} className="rounded-xl bg-slate-50 p-3 ring-1 ring-slate-200">
              <div className="flex items-center justify-between gap-2">
                <p className="text-[11px] font-semibold text-slate-600">{metric.label}</p>
                <Icon size={14} className="text-blue-600" />
              </div>
              <p className="mt-1 text-xl font-bold text-slate-900">
                {typeof metric.value === 'number' && metric.label !== 'SNS SMS Success Rate'
                  ? Math.round(metric.value).toLocaleString()
                  : metric.value.toFixed(1)}
                {metric.suffix}
              </p>
              <div className="mt-2 h-12">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={metric.series}>
                    <Line
                      type="monotone"
                      dataKey="value"
                      stroke="#2563eb"
                      strokeWidth={2}
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          );
        })}
      </div>
    </SectionCard>
  );
}
