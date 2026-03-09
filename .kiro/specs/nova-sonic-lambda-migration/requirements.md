# Requirements Document

## Introduction

Migrate the Nova Sonic Health Intake Voice Agent from a terminal Python app (`nova_sonic_health_intake_agent.py`) to a single AWS Lambda function behind an API Gateway WebSocket API. This is a hackathon prototype — minimal infrastructure, no Terraform, manual deploy via console or CLI. The Lambda maintains a long-lived WebSocket connection, streams audio bidirectionally between the browser client and Bedrock Nova Sonic, and runs the same deterministic state machine to collect health intake data.

## Glossary

- **Intake_Lambda**: Single Lambda function that handles WebSocket events and orchestrates the Bedrock Nova Sonic conversation.
- **Client**: Browser app that captures mic audio, sends it over WebSocket, and plays back received audio.
- **State_Machine**: The deterministic conversation controller: LANGUAGE_SELECT → ASKING → WAITING_USER → COUGH_PHASE → DONE.
- **Audio_Chunk**: Base64-encoded segment of PCM audio sent between Client and Lambda.

## Requirements

### Requirement 1: WebSocket Lambda Handler

**User Story:** As a developer, I want a single Lambda function that handles WebSocket connect, disconnect, and message events, so that the entire intake conversation runs serverlessly.

#### Acceptance Criteria

1. THE Lambda SHALL handle $connect, $disconnect, and $default routes from API Gateway v2 WebSocket API.
2. WHEN a $connect event arrives, THE Lambda SHALL initialize session state in memory (no external DB needed for prototype).
3. WHEN a $default message arrives with audio data, THE Lambda SHALL forward it to the active Bedrock Nova Sonic session.
4. THE Lambda SHALL send audio and control messages back to the Client via the API Gateway Management API.

### Requirement 2: Bedrock Nova Sonic Streaming

**User Story:** As a developer, I want the Lambda to manage a Bedrock bidirectional streaming session, so that voice conversation works the same as the terminal version.

#### Acceptance Criteria

1. THE Lambda SHALL open a Bedrock Nova Sonic bidirectional stream using the same model (amazon.nova-2-sonic-v1:0) and voice (arjun).
2. THE Lambda SHALL use the same system prompt as the terminal agent to constrain model behavior.
3. WHEN audio arrives from the Client, THE Lambda SHALL forward it to the Bedrock session as audioInput.
4. WHEN Bedrock produces audio output, THE Lambda SHALL forward it to the Client as base64-encoded audio.
5. WHEN Bedrock produces text output with USER role, THE Lambda SHALL use it for answer parsing.

### Requirement 3: State Machine and Answer Parsing

**User Story:** As a product owner, I want the same question flow and parsing logic, so that the Lambda produces identical results to the terminal agent.

#### Acceptance Criteria

1. THE Lambda SHALL execute the same 13-question intake flow: name, age, gender, 6 symptoms, 4 history fields.
2. THE Lambda SHALL use the same bilingual answer parsers (binary yes/no, age with Devanagari/Hindi words, gender with female-first ordering).
3. WHEN all questions are answered, THE Lambda SHALL transition to COUGH_PHASE.
4. THE Lambda SHALL support both English and Hindi language selection.

### Requirement 4: Cough Audio and Output

**User Story:** As a developer, I want cough audio uploaded to S3 and the final JSON produced, so that downstream ML and dashboard integrations work.

#### Acceptance Criteria

1. WHEN entering COUGH_PHASE, THE Lambda SHALL instruct the Client to record cough audio locally and send the WAV file.
2. THE Lambda SHALL upload the cough WAV to S3 under "health-intake/cough/" with a UUID filename.
3. THE Lambda SHALL produce the same output JSON schema: `{"body": "{\"name\":...,\"age\":...,\"gender\":...,...}", "cough_audio_s3": "s3://..."}`.
4. THE Lambda SHALL upload the final JSON to S3 under "health-intake/json/".

### Requirement 5: Lambda Configuration

**User Story:** As a developer, I want the Lambda properly configured so it can handle a full conversation.

#### Acceptance Criteria

1. THE Lambda SHALL use Python 3.12 runtime with 1024 MB memory and 900-second timeout.
2. THE Lambda execution role SHALL have permissions for Bedrock InvokeModelWithBidirectionalStream, S3 read/write, and API Gateway execute-api.
3. THE Lambda SHALL read S3_BUCKET and BEDROCK_MODEL_ID from environment variables.
4. THE Lambda SHALL be deployable via AWS Console or CLI (no Terraform required for prototype).
