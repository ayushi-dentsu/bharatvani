# Implementation Plan: Nova Sonic Lambda Migration

## Overview

Migrate the terminal-based Nova Sonic Health Intake Agent to a single AWS Lambda function behind an API Gateway v2 WebSocket API. Reuse the state machine, answer parsers, and Bedrock streaming logic from `nova_sonic_health_intake_agent.py`, replacing PyAudio I/O with WebSocket message passing. Add a minimal browser client for mic capture and audio playback.

## Tasks

- [x] 1. Create Lambda handler with WebSocket routing and answer parsers
  - [x] 1.1 Create `lambda_function.py` with `handler(event, context)` that routes `$connect`, `$disconnect`, and `$default` API Gateway v2 WebSocket events
    - On `$connect`: initialize an in-memory session dict (connection_id, state=LANGUAGE_SELECT, answers={}, language="English") and return 200
    - On `$disconnect`: clean up session state and return 200
    - On `$default`: parse the JSON message body and dispatch by `type` field (audio, cough_audio, control)
    - Store active sessions in a module-level dict keyed by `connectionId`
    - Initialize `apigatewaymanagementapi` boto3 client using the `requestContext.domainName` and `requestContext.stage` from the event
    - Read `S3_BUCKET` and `BEDROCK_MODEL_ID` from `os.environ`
    - _Requirements: 1.1, 1.2, 1.3, 5.3_

  - [x] 1.2 Copy answer parsers and constants from `nova_sonic_health_intake_agent.py`
    - Copy `IntakeQuestion` dataclass and `INTAKE_QUESTIONS` list (all 13 questions)
    - Copy `State` enum (LANGUAGE_SELECT, ASKING, WAITING_USER, COUGH_PHASE, DONE)
    - Copy word sets: `YES_WORDS`, `NO_WORDS`, `SKIP_WORDS`, `GENDER_MAP_ORDERED`
    - Copy parser functions: `is_skip()`, `parse_binary()`, `parse_age()`, `parse_gender()`, `detect_language_choice()`
    - Copy `ALL_BINARY_FIELDS` list
    - Copy audio constants: `INPUT_SAMPLE_RATE` (16000), `OUTPUT_SAMPLE_RATE` (24000)
    - _Requirements: 3.1, 3.2, 3.4_

- [x] 2. Implement BedrockStreamManager for Lambda
  - [x] 2.1 Create `BedrockStreamManager` class that manages the bidirectional Bedrock Nova Sonic stream
    - Port `NovaSonicClient.__init__` — remove PyAudio fields, keep asyncio queues (`audio_input_queue`, `audio_output_queue`), stream state flags (`is_active`, `_mute_mic`, `_assistant_speaking`, `_audio_played_for_turn`, `_assistant_audio_is_active`), and transcript lists
    - Port `_init_bedrock()` — same smithy SDK setup with `BedrockRuntimeClient`, `SigV4AuthScheme`, `EnvironmentCredentialsResolver`
    - Port `_send_event()` — same lock-protected send via `InvokeModelWithBidirectionalStreamInputChunk`
    - _Requirements: 2.1_

  - [x] 2.2 Port session lifecycle methods (`open_session`, `close_session`)
    - `open_session(system_prompt)`: same event sequence — sessionStart → promptStart → system TEXT contentStart/textInput/contentEnd → AUDIO contentStart for user input. Start `_response_loop` and `_audio_send_loop` as asyncio tasks. Remove `_start_audio_io()` call (no PyAudio)
    - `close_session()`: same teardown — contentEnd → promptEnd → sessionEnd → close stream. Cancel async tasks. Remove `_stop_audio_input/output` calls
    - _Requirements: 2.1, 2.2_

  - [x] 2.3 Port `_response_loop` — adapt audio/text output for WebSocket delivery
    - Same event parsing: contentStart, textOutput, audioOutput, contentEnd, error
    - On `audioOutput`: instead of putting bytes in `audio_output_queue` for PyAudio, base64-encode and send `{"type": "audio", "data": "..."}` to client via `post_to_connection()`
    - On `textOutput` with USER role: collect in `user_text_parts` for answer parsing (same as terminal)
    - On `textOutput` with ASSISTANT role: collect in `assistant_text_parts` AND send `{"type": "transcript", "role": "assistant", "text": "..."}` to client
    - Keep audio dedup logic (`_audio_played_for_turn` flag) — same as terminal agent
    - Keep barge-in detection (`{ "interrupted" : true }`)
    - _Requirements: 2.4, 2.5, 1.4_

  - [x] 2.4 Port `_audio_send_loop` — feed audio from WebSocket into Bedrock
    - Same drain loop: read from `audio_input_queue`, base64-encode, send as `audioInput` event
    - Audio is fed into the queue by the `$default` handler when it receives `{"type": "audio"}` messages from the client
    - Keep silence-sending behavior when `_mute_mic` is True (send zero bytes to keep stream alive)
    - _Requirements: 2.3_

  - [x] 2.5 Port `send_text()`, `instruct_and_wait_for_speech()`, `wait_for_user_response()`, `get_all_assistant_text()`
    - `send_text()`: identical — contentStart(TEXT) → textInput → contentEnd
    - `instruct_and_wait_for_speech()`: same wait logic but no playback queue drain (audio goes directly to client via WebSocket)
    - `wait_for_user_response()`: same settle-time logic with `user_text_parts`, same quick_answers fast path for binary questions
    - `get_all_assistant_text()`: identical
    - _Requirements: 2.2, 2.5_

- [x] 3. Implement ConversationManager (state machine)
  - [x] 3.1 Create `ConversationManager` class that orchestrates the intake conversation
    - Port `HealthIntakeAgent.__init__` — state, language, question_index, answers dict, cough_s3_uri. Replace `argparse.Namespace` with config from environment variables. Hold reference to `BedrockStreamManager` and `connection_id` for sending messages
    - Port `SYSTEM_PROMPT` constant — identical to terminal agent
    - Add helper `_send_to_client(message_dict)` that calls `apigatewaymanagementapi.post_to_connection()` with JSON-serialized message
    - Add `_send_state_update()` that sends `{"type": "state", "state": "...", "question": "..."}` to client on state transitions
    - _Requirements: 3.1, 1.4_

  - [x] 3.2 Port `_select_language()` — language selection phase
    - Same logic: instruct model to ask "English or Hindi?", wait for user response, call `detect_language_choice()`, retry up to MAX_RETRIES, default to English
    - Replace `_speak()` calls with `_instruct_and_wait()` (same as terminal `_speak` but no PyAudio)
    - Send state update `{"type": "state", "state": "LANGUAGE_SELECT"}` to client
    - _Requirements: 3.4_

  - [x] 3.3 Port `_ask_one()` — single question ask/answer cycle
    - Same flow: set state to ASKING, instruct model to ask question, wait for assistant to finish, unmute, set state to WAITING_USER, wait for user response
    - Same parsing dispatch: binary → `parse_binary()` → fallback `_model_interpret_binary()`, age → `parse_age()` → fallback `_model_interpret_age()`, gender → `parse_gender()`, text → raw string
    - Same retry logic (MAX_RETRIES=2) on no-input
    - Same skip detection via `is_skip()`
    - _Requirements: 3.1, 3.2_

  - [x] 3.4 Port `_model_interpret_binary()` and `_model_interpret_age()` — model fallback interpreters
    - Identical logic: send text instruction to model, wait for response, parse
    - _Requirements: 3.2_

  - [x] 3.5 Port `_build_output()` — final JSON construction
    - Same output schema: `{"body": "{\"name\":...,\"age\":...,\"gender\":...,...}", "cough_audio_s3": "s3://..."}`
    - Same field mapping: name (text), age (int), gender (M/F/O/U), binary fields (0/1)
    - _Requirements: 4.3_

  - [x] 3.6 Port cough phase and S3 uploads
    - Adapt `_cough_phase()`: instead of local PyAudio recording, send `{"type": "cough_start", "duration": 8}` to client, then wait for client to send back `{"type": "cough_audio", "data": "<base64 WAV>"}` via WebSocket
    - Close Nova session before cough phase (same as terminal)
    - On receiving cough WAV: decode base64, upload to S3 under `health-intake/cough/{uuid}.wav`
    - Port `S3Uploader` class — same `upload_cough_wav()` and `upload_final_json()` but accept bytes instead of file path for cough WAV
    - Upload final JSON to S3 under `health-intake/json/{uuid}.json`
    - Send `{"type": "result", "data": {...}}` to client when done
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [x] 3.7 Implement `run()` — main conversation orchestrator
    - Same sequence as terminal `HealthIntakeAgent.run()`: open session → select language → ask 13 questions → cough phase → thank user → build output → upload JSON
    - Wire into the `$default` handler: when `{"type": "control", "action": "start"}` arrives, spawn `run()` as an asyncio task
    - Feed incoming audio messages into `BedrockStreamManager.audio_input_queue`
    - Handle errors: send `{"type": "error", "message": "..."}` to client on exceptions
    - _Requirements: 1.3, 3.1, 3.3_

- [x] 4. Checkpoint — Lambda function complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Create browser client
  - [x] 5.1 Create `client/index.html` — single-page browser client
    - WebSocket connection to API Gateway endpoint (user pastes URL into a config field or JS constant)
    - Mic capture via Web Audio API: `AudioContext` at 16kHz, `ScriptProcessorNode` or `AudioWorklet` to get PCM 16-bit mono chunks
    - Send audio as `{"type": "audio", "data": "<base64 PCM>"}` over WebSocket
    - Receive and play audio: decode base64 PCM 24kHz, feed into `AudioContext` for playback
    - Display transcript messages (assistant and user) in a scrollable div
    - Display current state and question indicator
    - Start button that sends `{"type": "control", "action": "start"}`
    - Handle `cough_start` message: switch to cough recording mode, record WAV locally using MediaRecorder API, send as `{"type": "cough_audio", "data": "<base64 WAV>"}`
    - Handle `result` message: display final JSON output
    - Handle `error` message: display error to user
    - Minimal CSS — functional layout, nothing fancy
    - _Requirements: 1.4, 4.1_

- [x] 6. Create Dockerfile and deployment script
  - [x] 6.1 Create `Dockerfile` for Lambda container image
    - Base image: `public.ecr.aws/lambda/python:3.12`
    - Install dependencies: `boto3`, `aws-sdk-bedrock-runtime`, `smithy-aws-core`
    - Copy `lambda_function.py` into `${LAMBDA_TASK_ROOT}`
    - Set CMD to `lambda_function.handler`
    - _Requirements: 5.1, 5.4_

  - [x] 6.2 Create `deploy.sh` — CLI deployment script
    - Build and push container image to ECR
    - Create/update Lambda function with containe`r image, 1024 MB memory, 900s timeout
    - Set environment variables: `S3_BUCKET`, `BEDROCK_MODEL_ID`, `VOICE_ID`, `AWS_REGION`
    - Create IAM role with permissions for Bedrock `InvokeModelWithBidirectionalStream`, S3 read/write, API Gateway `execute-api`
    - Create API Gateway v2 WebSocket API with `$connect`, `$disconnect`, `$default` routes `pointing to the Lambda
    - Output the WebSocket URL for the client
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

- [x] 7. Final checkpoint — Full integration
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- The Lambda reuses all parsing logic and state machine from the terminal agent — the migration is primarily an I/O swap (PyAudio → WebSocket)
- No DynamoDB or Terraform — this is a hackathon prototype with manual CLI deployment
