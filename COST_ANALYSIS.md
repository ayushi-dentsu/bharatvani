# BharatVani Cost Analysis — Actual Architecture

## Architecture Summary

| Component | AWS Service | Config |
|-----------|------------|--------|
| Frontend | CloudFront + S3 | Static React app |
| WebSocket Server | ECS Fargate | 1 vCPU, 2 GB RAM, always-on |
| Voice AI | Amazon Nova Sonic (Bedrock) | Bidirectional streaming STT+TTS |
| Audio Predictor | Lambda (Docker, 1024 MB, 60s timeout) | librosa + XGBoost ML inference |
| Cough Predictor | Lambda (Docker, 512 MB, 60s timeout) | scikit-learn + XGBoost ML inference |
| Screening Aggregator | Lambda (Python, 256 MB, 60s timeout) | Calls Nova Lite LLM |
| Get Screening API | Lambda (Python, 128 MB) + API Gateway HTTP | DynamoDB read |
| Report Generation | Amazon Nova Lite (Bedrock) | ~1K token prompt, ~500 token response |
| Storage | S3 (recordings) + DynamoDB (screenings) | On-demand |
| Load Balancer | ALB | HTTP listener, 1 target |

---

## Per-Screening Cost Breakdown

Assumptions per screening:
- ~3 minute voice conversation with Nova Sonic
- 1 WAV cough recording (~150 KB) + 1 JSON file (~1 KB) uploaded to S3
- 3 Lambda invocations (audio predictor, cough predictor, aggregator)
- 1 Nova Lite LLM call for report generation
- 1 API Gateway call to poll results
- 1 DynamoDB write (ECS) + 3 updates (2 ML + 1 aggregator) + ~10 reads (polling)


### 1. Amazon Nova Sonic (Voice Conversation)

| Metric | Value |
|--------|-------|
| Speech input tokens | ~$0.0034 / 1K tokens |
| Speech output tokens | ~$0.0136 / 1K tokens |
| Estimated per 3-min call | ~$0.05 |

A 3-minute bidirectional voice session generates roughly 1.5K speech input tokens and 1.5K speech output tokens.

**Cost per screening: ~$0.05 (₹4.13)**

### 2. ECS Fargate (WebSocket Server — Always On)

| Resource | Rate | Monthly |
|----------|------|---------|
| 1 vCPU | $0.04048/hr | $29.55 |
| 2 GB RAM | $0.004445/GB/hr × 2 | $6.49 |
| **Total** | **$0.049/hr** | **$36.04/month** |

This is a fixed cost — the ECS task runs 24/7 regardless of screening volume.

**Per screening (at 100/month): $0.36**
**Per screening (at 1,000/month): $0.036**
**Per screening (at 10,000/month): $0.0036**

### 3. Audio Predictor Lambda

| Config | Value |
|--------|-------|
| Memory | 1024 MB (1 GB) |
| Avg duration | ~8 seconds |
| GB-seconds | 8 |
| Cost/GB-sec | $0.0000166667 |

Compute: 8 × $0.0000166667 = $0.000133
Request: $0.0000002

**Cost per screening: ~$0.00014 (₹0.012)**

### 4. Cough Predictor Lambda

| Config | Value |
|--------|-------|
| Memory | 512 MB (0.5 GB) |
| Avg duration | ~3 seconds |
| GB-seconds | 1.5 |
| Cost/GB-sec | $0.0000166667 |

Compute: 1.5 × $0.0000166667 = $0.000025
Request: $0.0000002

**Cost per screening: ~$0.000025 (₹0.002)**

### 5. Screening Aggregator Lambda + Nova Lite

| Component | Detail |
|-----------|--------|
| Lambda: 256 MB, ~5s | $0.000021 |
| Nova Lite input: ~1K tokens @ $0.06/1M | $0.00006 |
| Nova Lite output: ~500 tokens @ $0.24/1M | $0.00012 |

**Cost per screening: ~$0.0002 (₹0.017)**

### 6. Get Screening Lambda + API Gateway

| Component | Detail |
|-----------|--------|
| Lambda: 128 MB, ~0.2s, ~10 polls | $0.000004 |
| API Gateway HTTP: $1/million requests × 10 | $0.00001 |

**Cost per screening: ~$0.00002 (₹0.002)**

### 7. S3 Storage & Requests

| Item | Cost |
|------|------|
| WAV storage (~150 KB) | negligible |
| JSON storage (~1 KB) | negligible |
| PUT requests (2) | $0.00001 |
| GET requests (model download, cached) | negligible |

**Cost per screening: ~$0.00001 (₹0.001)**

### 8. DynamoDB

| Operation | Count | Cost |
|-----------|-------|------|
| Write (1 WCU each) | 4 (1 put + 3 updates) | $0.00000500 |
| Read (1 RCU each) | ~10 (polling) | $0.00000250 |

**Cost per screening: ~$0.000008 (₹0.001)**

### 9. CloudFront

| Item | Cost |
|------|------|
| Data transfer (static assets, cached) | negligible per request |
| WebSocket proxy data (~1 MB/session) | ~$0.00008 |
| HTTPS requests | ~$0.00001 |

**Cost per screening: ~$0.0001 (₹0.008)**

### 10. DynamoDB Streams

| Item | Cost |
|------|------|
| Read requests (4 stream records) | $0.000008 |

**Cost per screening: ~$0.00001 (₹0.001)**

---

## Total Per-Screening Cost

| Component | Cost (USD) | Cost (INR) | % of Total |
|-----------|-----------|-----------|------------|
| Nova Sonic (3-min voice) | $0.0500 | ₹4.130 | 97.1% |
| S3 + DynamoDB + Streams | $0.0001 | ₹0.005 | 0.1% |
| Audio Predictor Lambda | $0.0001 | ₹0.012 | 0.3% |
| Cough Predictor Lambda | $0.0000 | ₹0.002 | 0.0% |
| Aggregator + Nova Lite | $0.0002 | ₹0.017 | 0.4% |
| Get Screening + API GW | $0.0000 | ₹0.002 | 0.0% |
| CloudFront | $0.0001 | ₹0.008 | 0.2% |
| **Variable Total** | **$0.0515** | **₹4.25** | **100%** |

> Nova Sonic dominates the per-screening cost at ~97%.

---

## Monthly Cost Projections (Variable + Fixed)

| Volume | Nova Sonic | Lambdas | S3/DDB | ECS Fargate | ALB ($0.0225/hr + LCU) | CloudFront | **Total** |
|--------|-----------|---------|--------|-------------|------------------------|------------|-----------|
| 100/mo | $5.00 | $0.04 | $0.01 | $36.04 | $16.50 | $0.01 | **$57.60** |
| 500/mo | $25.00 | $0.18 | $0.05 | $36.04 | $16.50 | $0.05 | **$77.82** |
| 1,000/mo | $50.00 | $0.37 | $0.10 | $36.04 | $16.50 | $0.10 | **$103.11** |
| 5,000/mo | $250.00 | $1.83 | $0.50 | $36.04 | $16.50 | $0.50 | **$305.37** |
| 10,000/mo | $500.00 | $3.65 | $1.00 | $36.04 | $16.50 | $1.00 | **$558.19** |

### Fixed Monthly Costs (regardless of volume)

| Service | Monthly Cost |
|---------|-------------|
| ECS Fargate (1 vCPU, 2 GB, 24/7) | $36.04 |
| ALB (base hourly charge) | $16.43 |
| CloudWatch Logs | ~$2.00 |
| S3 storage (cumulative) | ~$0.50 |
| **Fixed Total** | **~$55/month** |

---

## Cost Per Screening at Scale

| Monthly Volume | Variable/screening | Fixed/screening | **Total/screening** |
|---------------|-------------------|-----------------|---------------------|
| 100 | $0.051 | $0.550 | **$0.601 (₹49.6)** |
| 500 | $0.051 | $0.110 | **$0.161 (₹13.3)** |
| 1,000 | $0.051 | $0.055 | **$0.106 (₹8.8)** |
| 5,000 | $0.051 | $0.011 | **$0.062 (₹5.1)** |
| 10,000 | $0.051 | $0.006 | **$0.057 (₹4.7)** |

> At 1,000+ screenings/month, cost drops below ₹9 per screening.
> At 5,000+, it approaches the theoretical minimum of ~₹4.25 (Nova Sonic floor).

---

## Hackathon Demo Cost Estimate

For a 48-hour hackathon with ~50 demo screenings:

| Item | Cost |
|------|------|
| ECS Fargate (2 days) | $2.35 |
| ALB (2 days) | $1.08 |
| Nova Sonic (50 × $0.05) | $2.50 |
| Lambdas (50 calls) | $0.02 |
| S3 + DynamoDB | $0.01 |
| CloudFront | $0.01 |
| **Total hackathon cost** | **~$6 (₹495)** |

---

## Key Insights

1. **Nova Sonic is 97% of variable cost** — the ML pipeline (Lambdas, Nova Lite, storage) is essentially free at this scale.

2. **ECS Fargate is the main fixed cost** — $36/month for a single always-on task. Could be reduced by:
   - Scaling to zero when idle (but adds cold start latency)
   - Using Fargate Spot (~70% discount) for non-production
   - Moving to EC2 t3.micro (~$8/month) for low-traffic scenarios

3. **ALB adds $16/month fixed** — could be eliminated by connecting directly to ECS public IP (already supported via `?ecs_ip=` query param), but loses health checks and stable DNS.

4. **Nova Lite (aggregator LLM) is negligible** — at $0.06/1M input tokens, it costs fractions of a cent per call.

5. **Lambda free tier covers early usage** — 400K GB-seconds/month free means the first ~50K screenings/month have zero Lambda compute cost.

---

## Comparison: BharatVani vs Traditional Telehealth

| Metric | BharatVani | Traditional IVR + Doctor |
|--------|-----------|-------------------------|
| Cost per screening | ₹4.25–₹50 | ₹200–₹500 |
| Setup cost | ~₹500 (hackathon) | ₹5–10 lakhs |
| Monthly fixed | ₹4,500 | ₹50,000+ |
| Scaling | Automatic | Manual staffing |
| Languages | Hindi + English (AI) | Per-agent |
| Availability | 24/7 | Business hours |

---

*Pricing based on AWS us-east-1 on-demand rates. Sources: [AWS Fargate Pricing](https://aws.amazon.com/fargate/pricing/), [AWS Lambda Pricing](https://aws.amazon.com/lambda/pricing/), [Amazon Nova Pricing](https://aws.amazon.com/nova/pricing/), [AWS Bedrock Pricing](https://aws.amazon.com/bedrock/pricing/). Nova Sonic pricing from published rates (~$0.017/min). Content rephrased for compliance with licensing restrictions.*
