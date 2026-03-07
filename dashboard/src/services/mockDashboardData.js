const languages = ['Hindi', 'English'];

const stateSeed = [
  { name: 'UP', coords: [80.9462, 26.8467], screenings: 560, highRisk: 182 },
  { name: 'Bihar', coords: [85.1376, 25.5941], screenings: 430, highRisk: 145 },
  { name: 'Maharashtra', coords: [75.7139, 19.7515], screenings: 390, highRisk: 104 },
  { name: 'Karnataka', coords: [76.6394, 15.3173], screenings: 320, highRisk: 79 },
  { name: 'Rajasthan', coords: [74.2179, 27.0238], screenings: 280, highRisk: 65 }
];

const nowLabel = () =>
  new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

const randomInt = (min, max) =>
  Math.floor(Math.random() * (max - min + 1)) + min;

const randomPhone = () => {
  const digits = `${randomInt(6000000000, 9999999999)}`;
  return `+91 ${digits.slice(0, 5)} ${digits.slice(5)}`;
};

const randomWaveform = () =>
  Array.from({ length: 42 }, (_, index) => {
    const swing = index % 4 === 0 ? 30 : 10;
    return randomInt(14, 74) + swing;
  });

const nextSparkline = (series, nextValue, max = 18) => {
  const updated = [...series.slice(-(max - 1)), { value: nextValue }];
  return updated;
};

const createScreening = (idSeed) => {
  const riskRoll = randomInt(1, 100);
  const confidence = randomInt(63, 98);
  const language = languages[randomInt(0, 1)];

  return {
    id: `BV-${idSeed.toString().padStart(6, '0')}`,
    phone: randomPhone(),
    language,
    riskLevel: riskRoll > 72 ? 'HIGH' : 'LOW',
    confidence,
    timestamp: new Date().toLocaleString()
  };
};

export const createInitialDashboardState = () => {
  const screeningsPerHour = Array.from({ length: 10 }, (_, i) => ({
    time: `${(8 + i).toString().padStart(2, '0')}:00`,
    screenings: randomInt(35, 92)
  }));

  const awsBase = {
    lambdaInvocations: { label: 'Lambda Invocations', value: 5180, series: [{ value: 5000 }, { value: 5058 }, { value: 5102 }, { value: 5180 }], suffix: '' },
    lambdaLatency: { label: 'Lambda Latency', value: 230, series: [{ value: 250 }, { value: 245 }, { value: 236 }, { value: 230 }], suffix: 'ms' },
    dynamoWrites: { label: 'DynamoDB Writes', value: 4820, series: [{ value: 4600 }, { value: 4695 }, { value: 4750 }, { value: 4820 }], suffix: '' },
    s3Uploads: { label: 'S3 Audio Uploads', value: 5115, series: [{ value: 4900 }, { value: 4975 }, { value: 5058 }, { value: 5115 }], suffix: '' },
    snsSmsSuccess: { label: 'SNS SMS Success Rate', value: 98.4, series: [{ value: 96.2 }, { value: 97.1 }, { value: 97.9 }, { value: 98.4 }], suffix: '%' }
  };

  const recentScreenings = Array.from({ length: 8 }, (_, index) =>
    createScreening(11000 + index)
  );

  const highRiskDetected = recentScreenings.filter((s) => s.riskLevel === 'HIGH').length + 320;
  const totalScreenings = 12840;

  return {
    tick: 11008,
    flowStep: 0,
    status: 'AI extracting voice biomarkers...',
    counters: {
      totalScreenings,
      highRiskDetected,
      avgConfidence: 86,
      ivrCallsToday: 10620,
      smsSent: 10204
    },
    liveCallMetrics: {
      callsReceived: 10620,
      audioProcessed: 10470,
      inferenceTimeMs: 228,
      smsDeliveryRate: 98.2
    },
    waveform: randomWaveform(),
    featureSet: ['MFCC', 'Frequency Spectrum', 'Zero Crossing Rate', 'Spectral Centroid'],
    inference: {
      respiratoryRisk: 72,
      cardiacPattern: 38,
      speechDegradation: 44,
      mentalHealthIndicators: 41,
      riskLevel: 'HIGH',
      confidenceScore: 82
    },
    screeningsPerHour,
    languageUsage: [
      { name: 'Hindi', value: 73 },
      { name: 'English', value: 27 }
    ],
    stateHeat: stateSeed,
    awsMetrics: awsBase,
    recentScreenings,
    searchTerm: ''
  };
};

export const simulateDashboardTick = (previousState) => {
  const tick = previousState.tick + 1;
  const newScreening = createScreening(tick);
  const highRiskIncrement = newScreening.riskLevel === 'HIGH' ? 1 : 0;

  const randomStateIndex = randomInt(0, previousState.stateHeat.length - 1);
  const nextStateHeat = previousState.stateHeat.map((state, index) => {
    if (index !== randomStateIndex) return state;

    return {
      ...state,
      screenings: state.screenings + 1,
      highRisk: state.highRisk + highRiskIncrement
    };
  });

  const latestHour = nowLabel();
  const lastHourBucket = previousState.screeningsPerHour[previousState.screeningsPerHour.length - 1];
  const nextHourSeries =
    lastHourBucket && lastHourBucket.time === latestHour
      ? [
          ...previousState.screeningsPerHour.slice(0, -1),
          { ...lastHourBucket, screenings: lastHourBucket.screenings + 1 }
        ]
      : [...previousState.screeningsPerHour.slice(-11), { time: latestHour, screenings: 1 }];

  const nextHindi = previousState.languageUsage[0].value + (newScreening.language === 'Hindi' ? 1 : 0);
  const nextEnglish = previousState.languageUsage[1].value + (newScreening.language === 'English' ? 1 : 0);
  const languageTotal = nextHindi + nextEnglish;

  const respiratoryRisk = randomInt(28, 88);
  const cardiacPattern = randomInt(20, 76);
  const speechDegradation = randomInt(18, 70);
  const mentalHealthIndicators = randomInt(16, 66);
  const confidenceScore = randomInt(62, 97);
  const riskLevel = respiratoryRisk > 66 || cardiacPattern > 68 ? 'HIGH' : 'LOW';

  const nextAwsMetrics = {
    lambdaInvocations: {
      ...previousState.awsMetrics.lambdaInvocations,
      value: previousState.awsMetrics.lambdaInvocations.value + randomInt(1, 3),
      series: nextSparkline(
        previousState.awsMetrics.lambdaInvocations.series,
        previousState.awsMetrics.lambdaInvocations.value + randomInt(1, 3)
      )
    },
    lambdaLatency: {
      ...previousState.awsMetrics.lambdaLatency,
      value: randomInt(180, 320),
      series: nextSparkline(
        previousState.awsMetrics.lambdaLatency.series,
        randomInt(180, 320)
      )
    },
    dynamoWrites: {
      ...previousState.awsMetrics.dynamoWrites,
      value: previousState.awsMetrics.dynamoWrites.value + randomInt(1, 3),
      series: nextSparkline(
        previousState.awsMetrics.dynamoWrites.series,
        previousState.awsMetrics.dynamoWrites.value + randomInt(1, 3)
      )
    },
    s3Uploads: {
      ...previousState.awsMetrics.s3Uploads,
      value: previousState.awsMetrics.s3Uploads.value + 1,
      series: nextSparkline(
        previousState.awsMetrics.s3Uploads.series,
        previousState.awsMetrics.s3Uploads.value + 1
      )
    },
    snsSmsSuccess: {
      ...previousState.awsMetrics.snsSmsSuccess,
      value: Math.min(99.9, Math.max(94.5, previousState.awsMetrics.snsSmsSuccess.value + (Math.random() - 0.5) * 0.6)),
      series: nextSparkline(
        previousState.awsMetrics.snsSmsSuccess.series,
        Math.min(99.9, Math.max(94.5, previousState.awsMetrics.snsSmsSuccess.value + (Math.random() - 0.5) * 0.6))
      )
    }
  };

  return {
    ...previousState,
    tick,
    flowStep: (previousState.flowStep + 1) % 5,
    status: previousState.flowStep % 2 === 0 ? 'AI extracting voice biomarkers...' : 'Lambda inference completed. Preparing SMS...',
    counters: {
      totalScreenings: previousState.counters.totalScreenings + 1,
      highRiskDetected: previousState.counters.highRiskDetected + highRiskIncrement,
      avgConfidence: Math.round((previousState.counters.avgConfidence * 9 + confidenceScore) / 10),
      ivrCallsToday: previousState.counters.ivrCallsToday + 1,
      smsSent: previousState.counters.smsSent + 1
    },
    liveCallMetrics: {
      callsReceived: previousState.liveCallMetrics.callsReceived + 1,
      audioProcessed: previousState.liveCallMetrics.audioProcessed + 1,
      inferenceTimeMs: randomInt(180, 340),
      smsDeliveryRate: Math.min(99.9, Math.max(95.2, previousState.liveCallMetrics.smsDeliveryRate + (Math.random() - 0.5) * 0.5))
    },
    waveform: randomWaveform(),
    inference: {
      respiratoryRisk,
      cardiacPattern,
      speechDegradation,
      mentalHealthIndicators,
      riskLevel,
      confidenceScore
    },
    screeningsPerHour: nextHourSeries,
    languageUsage: [
      { name: 'Hindi', value: Number(((nextHindi / languageTotal) * 100).toFixed(1)) },
      { name: 'English', value: Number(((nextEnglish / languageTotal) * 100).toFixed(1)) }
    ],
    stateHeat: nextStateHeat,
    awsMetrics: nextAwsMetrics,
    recentScreenings: [newScreening, ...previousState.recentScreenings].slice(0, 15)
  };
};
