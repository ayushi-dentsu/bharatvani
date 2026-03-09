# Design Document

## Overview

Single Lambda function behind an API Gateway v2 WebSocket API. The Lambda maintains a long-lived bidirectional Bedrock Nova Sonic stream for the duration of each WebSocket connection. A browser client handles mic capture and audio playback. The Lambda reuses the same state machine, answer parsers, and output schema from the terminal agent.

## Architecture

```
Browser Client ←→ API Gateway v2 (WebSocket) ←→ Lambda (Python 3.12)
                                                    ↕
                                              Bedrock Nova Sonic
                                                    ↕
                                                  S3 Bucket
```

The Lambda is invoked once per WebSocket connection and stays alive for the full conversation (up to 15 min timeout). It uses response streaming to keep the connection open while the Bedrock bidirectional stream runs.

## Key Design Decision: Lambda Response Streaming

The Lambda uses the `RESPONSE_STREAM` invocation mode with API Gateway v2. This allows the Lambda to:
1. Stay alive for the full conversation duration (up to 900s)
2. Continuously receive audio from the client via API Gateway
3. Send audio back to the client via the API Gateway Management API (`@connections` endpoint)

This avoids the need for DynamoDB state persistence between invocations — the entire conversation happens within a single Lambda execution.

## WebSocket Message Protocol

### Client → Lambda

```json
{"type": "audio", "data": "<base64 PCM 16kHz mono 16-bit>"}
{"type": "cough_audio", "data": "<base64 WAV file>"}
{"type": "control", "action": "start"}
```

### Lambda → Client

```json
{"type": "audio", "data": "<base64 PCM 24kHz mono 16-bit>"}
{"type": "transcript", "role": "assistant|user", "text": "..."}
{"type": "state", "state": "LANGUAGE_SELECT|ASKING|WAITING_USER|COUGH_PHASE|DONE", "question": "name"}
{"type": "cough_start", "duration": 8}
{"type": "result", "data": {"body": "{...}", "cough_audio_s3": "s3://..."}}
{"type": "error", "message": "..."}
```

## Components

### 1. `lambda_function.py` — Lambda Handler

Single file containing:

- **`handler(event, context)`**: Routes `$connect`, `$disconnect`, `$default` events. On `$connect`, spawns the async conversation loop. On `$default`, feeds audio into the Bedrock stream. On `$disconnect`, cleans up.

- **`ConversationManager`**: Replaces `HealthIntakeAgent`. Same state machine (LANGUAGE_SELECT → ASKING → WAITING_USER → COUGH_PHASE → DONE), same question list, same parsers. Instead of PyAudio, it:
  - Receives audio chunks from the WebSocket event payload
  - Sends audio back via `apigatewaymanagementapi.post_to_connection()`
  - Sends state/transcript updates as JSON messages

- **`BedrockStreamManager`**: Replaces `NovaSonicClient`. Same Bedrock SDK usage (smithy client, bidirectional stream), but:
  - No PyAudio — audio comes from/goes to WebSocket
  - Audio input queue fed by WebSocket messages instead of mic callback
  - Audio output sent to client via API Gateway Management API instead of speaker

- **Answer parsers**: Copied directly from terminal agent — `parse_binary()`, `parse_age()`, `parse_gender()`, `detect_language_choice()`, `is_skip()`, and all word sets (YES_WORDS, NO_WORDS, etc.)

- **S3Uploader**: Same as terminal agent, using boto3.

### 2. `client/index.html` — Browser Client (Single Page)

Minimal HTML/JS page that:
- Connects to the WebSocket API endpoint
- Captures mic audio via Web Audio API (16kHz mono PCM)
- Sends audio chunks as base64 JSON messages
- Receives and plays back audio from Lambda (24kHz PCM)
- Shows transcript and state updates in the UI
- Handles cough recording phase locally (records WAV, sends as `cough_audio` message)

### 3. Lambda Deployment

Manual deploy via AWS CLI (hackathon-style):
- Package `lambda_function.py` + dependencies into a zip or container image
- The smithy SDK (`aws-sdk-bedrock-runtime`) requires a Lambda layer or container image since it's not in the default Lambda runtime
- Environment variables: `S3_BUCKET`, `BEDROCK_MODEL_ID`, `VOICE_ID`, `AWS_REGION`

## What Changes from Terminal Agent

| Aspect | Terminal Agent | Lambda |
|--------|---------------|--------|
| Audio I/O | PyAudio (local mic/speaker) | WebSocket (browser mic/speaker) |
| Entry point | `asyncio.run(async_main())` | `handler(event, context)` |
| Audio input | Mic callback → queue | WebSocket message → queue |
| Audio output | Queue → speaker stream | Queue → API Gateway post_to_connection |
| Cough recording | Local PyAudio recording | Client records, sends WAV over WebSocket |
| Beep sound | PyAudio sine wave | Client plays beep locally |
| State persistence | In-memory (single process) | In-memory (single Lambda invocation) |
| Dependencies | pyaudio, boto3, smithy SDK | boto3, smithy SDK (no pyaudio) |

## What Stays the Same

- Bedrock Nova Sonic bidirectional streaming protocol (sessionStart → promptStart → contentStart → audioInput/textInput → contentEnd → promptEnd → sessionEnd)
- System prompt
- State machine: LANGUAGE_SELECT → ASKING → WAITING_USER → COUGH_PHASE → DONE
- All 13 intake questions in order
- Answer parsing: binary (bilingual), age (Devanagari + Hindi words), gender (female-first), language detection
- Audio dedup logic (`_audio_played_for_turn` flag)
- Mic muting during assistant speech (send silence bytes)
- Output JSON schema: `{"body": "{...}", "cough_audio_s3": "s3://..."}`
- S3 upload paths: `health-intake/cough/`, `health-intake/json/`

## Deployment Notes

Since `aws-sdk-bedrock-runtime` (smithy SDK) isn't available in the default Lambda Python runtime, the Lambda needs to be deployed as a container image:

```dockerfile
FROM public.ecr.aws/lambda/python:3.12
COPY lambda_function.py ${LAMBDA_TASK_ROOT}/
RUN pip install boto3 aws-sdk-bedrock-runtime smithy-aws-core
CMD ["lambda_function.handler"]
```

API Gateway v2 WebSocket API setup (via Console or CLI):
- Create WebSocket API with `$connect`, `$disconnect`, `$default` routes
- Point all routes to the same Lambda function
- Note the WebSocket URL for the client
