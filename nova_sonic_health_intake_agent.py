#!/usr/bin/env python3
"""
Nova 2 Sonic – Multilingual Health Intake Voice Agent
=====================================================
Single-file terminal app using AWS Bedrock Nova 2 Sonic bidirectional streaming.
Deterministic state-machine controls the conversation (no free-form dialogue).

Dependencies:
    pip install pyaudio boto3 aws-sdk-bedrock-runtime smithy-aws-core

Run:
    python nova_sonic_health_intake_agent.py --s3-bucket my-bucket
    python nova_sonic_health_intake_agent.py --s3-bucket my-bucket --voice-id arjun --debug-events
    python nova_sonic_health_intake_agent.py --list-audio-devices
"""

import argparse
import asyncio
import base64
import json
import math
import os
import struct
import sys
import time
import uuid
import wave
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Optional

import boto3
import pyaudio
from aws_sdk_bedrock_runtime.client import (
    BedrockRuntimeClient,
    InvokeModelWithBidirectionalStreamOperationInput,
)
from aws_sdk_bedrock_runtime.config import Config, HTTPAuthSchemeResolver, SigV4AuthScheme
from aws_sdk_bedrock_runtime.models import (
    BidirectionalInputPayloadPart,
    InvokeModelWithBidirectionalStreamInputChunk,
)
from smithy_aws_core.credentials_resolvers.environment import EnvironmentCredentialsResolver

# ─── Audio constants ────────────────────────────────────────────────────────────
INPUT_SAMPLE_RATE = 16000
OUTPUT_SAMPLE_RATE = 24000
CHANNELS = 1
FORMAT = pyaudio.paInt16
CHUNK_SIZE = 1024

# ─── Intake field definitions ───────────────────────────────────────────────────
SYMPTOM_FIELDS = ["fever", "cold", "cough", "fatigue", "loss_of_smell", "breathing_difficulties"]
HISTORY_FIELDS = ["asthma", "diabetes", "hypertension", "smoker"]
ALL_BINARY_FIELDS = SYMPTOM_FIELDS + HISTORY_FIELDS

# ─── State machine ──────────────────────────────────────────────────────────────
class State(Enum):
    LANGUAGE_SELECT = auto()
    ASKING = auto()
    WAITING_USER = auto()
    COUGH_PHASE = auto()
    DONE = auto()


# ─── Logging ─────────────────────────────────────────────────────────────────────
DEBUG_EVENTS = False
DEBUG_AUDIO = False

def ts() -> str:
    """Timestamped prefix for log lines."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

def log_event(msg: str) -> None:
    if DEBUG_EVENTS:
        print(f"[{ts()}] [EVENT] {msg}")

def log_audio(msg: str) -> None:
    if DEBUG_AUDIO:
        print(f"[{ts()}] [AUDIO] {msg}")

def log_info(msg: str) -> None:
    print(f"[{ts()}] {msg}")


# ─── Utility ─────────────────────────────────────────────────────────────────────
def pcm16_rms(data: bytes) -> float:
    """Compute RMS of 16-bit PCM data."""
    n = len(data) // 2
    if n == 0:
        return 0.0
    samples = struct.unpack(f"<{n}h", data[:n * 2])
    return math.sqrt(sum(s * s for s in samples) / n)


# ─── Questions definition ────────────────────────────────────────────────────────
@dataclass
class IntakeQuestion:
    key: str                    # field name in output
    english: str                # question text in English
    hindi: str                  # question text in Hindi
    field_type: str = "text"    # "text", "binary", "age", "gender"

INTAKE_QUESTIONS: list[IntakeQuestion] = [
    IntakeQuestion("name",   "What is your full name?", "आपका पूरा नाम क्या है?", "text"),
    IntakeQuestion("age",    "How old are you?", "आपकी उम्र क्या है?", "age"),
    IntakeQuestion("gender", "What is your gender? Male, Female, or Other?",
                   "आपका लिंग क्या है? पुरुष, महिला, या अन्य?", "gender"),
    # Symptoms
    IntakeQuestion("fever",   "Do you have fever? Yes or No.", "क्या आपको बुखार है? हाँ या नहीं।", "binary"),
    IntakeQuestion("cold",    "Do you have cold? Yes or No.", "क्या आपको सर्दी है? हाँ या नहीं।", "binary"),
    IntakeQuestion("cough",   "Do you have cough? Yes or No.", "क्या आपको खांसी है? हाँ या नहीं।", "binary"),
    IntakeQuestion("fatigue", "Do you have fatigue? Yes or No.", "क्या आपको थकान है? हाँ या नहीं।", "binary"),
    IntakeQuestion("loss_of_smell", "Have you lost your sense of smell? Yes or No.",
                   "क्या आपकी सूंघने की शक्ति कम हुई है? हाँ या नहीं।", "binary"),
    IntakeQuestion("breathing_difficulties", "Do you have breathing difficulties? Yes or No.",
                   "क्या आपको सांस लेने में कठिनाई है? हाँ या नहीं।", "binary"),
    # History
    IntakeQuestion("asthma",       "Do you have asthma? Yes or No.", "क्या आपको अस्थमा है? हाँ या नहीं।", "binary"),
    IntakeQuestion("diabetes",     "Do you have diabetes? Yes or No.", "क्या आपको मधुमेह है? हाँ या नहीं।", "binary"),
    IntakeQuestion("hypertension", "Do you have hypertension? Yes or No.",
                   "क्या आपको उच्च रक्तचाप है? हाँ या नहीं।", "binary"),
    IntakeQuestion("smoker",       "Are you a smoker? Yes or No.", "क्या आप धूम्रपान करते हैं? हाँ या नहीं।", "binary"),
]


# ─── Answer parsing helpers ──────────────────────────────────────────────────────
YES_WORDS = {
    "yes", "yeah", "yep", "yup", "sure", "correct", "right", "affirmative",
    "हाँ", "हां", "जी", "जी हाँ", "ha", "haan", "ji",
}
NO_WORDS = {
    "no", "nope", "nah", "negative", "not",
    "नहीं", "ना", "नही", "nahi", "nahin",
}
SKIP_WORDS = {
    "skip", "please skip", "next", "pass",
    "स्किप", "छोड़ो", "छोड़िए", "अगला",
}
GENDER_MAP = {
    "male": "M", "man": "M", "boy": "M", "m": "M",
    "पुरुष": "M", "आदमी": "M", "लड़का": "M",
    "female": "F", "woman": "F", "girl": "F", "f": "F",
    "महिला": "F", "औरत": "F", "लड़की": "F",
    "other": "O", "others": "O", "non-binary": "O", "nonbinary": "O",
    "अन्य": "O",
}


def is_skip(text: str) -> bool:
    return text.strip().lower() in SKIP_WORDS


def parse_binary(text: str) -> Optional[int]:
    """Return 1 for yes, 0 for no, None if unclear."""
    t = text.strip().lower()
    tokens = set(t.split())
    if tokens & YES_WORDS or t in YES_WORDS:
        return 1
    if tokens & NO_WORDS or t in NO_WORDS:
        return 0
    # Fallback: check if any yes/no word is a substring
    for w in YES_WORDS:
        if w in t:
            return 1
    for w in NO_WORDS:
        if w in t:
            return 0
    return None


def parse_age(text: str) -> Optional[int]:
    """Extract first integer from text as age."""
    digits = "".join(ch if ch.isdigit() else " " for ch in text)
    for tok in digits.split():
        try:
            v = int(tok)
            if 0 < v < 150:
                return v
        except ValueError:
            pass
    return None


def parse_gender(text: str) -> str:
    """Map text to M/F/O, default U."""
    t = text.strip().lower()
    for key, val in GENDER_MAP.items():
        if key in t:
            return val
    return "U"


def detect_language_choice(text: str) -> Optional[str]:
    """Detect English or Hindi from user utterance."""
    t = text.strip().lower()
    eng_markers = ["english", "inglish", "अंग्रेज", "एंग्लिश", "angrez"]
    hindi_markers = ["hindi", "हिंदी", "हिन्दी"]
    for m in eng_markers:
        if m in t:
            return "English"
    for m in hindi_markers:
        if m in t:
            return "Hindi"
    return None


# ═══════════════════════════════════════════════════════════════════════════════
#  Nova Sonic Bidirectional Streaming Client
# ═══════════════════════════════════════════════════════════════════════════════
class NovaSonicClient:
    """
    Manages a single bidirectional streaming session with Bedrock Nova 2 Sonic.
    Follows the reference sample's event-loop architecture:
        sessionStart → promptStart → contentStart → audioInput/textInput →
        contentEnd → promptEnd → sessionEnd
    """

    def __init__(
        self,
        model_id: str,
        region: str,
        voice_id: str,
        input_device_index: Optional[int] = None,
        output_device_index: Optional[int] = None,
    ):
        self.model_id = model_id
        self.region = region
        self.voice_id = voice_id
        self.input_device_index = input_device_index
        self.output_device_index = output_device_index

        self.bedrock_client: Optional[BedrockRuntimeClient] = None
        self.stream = None
        self.is_active = False

        # Asyncio primitives
        self._send_lock = asyncio.Lock()  # serialize all sends to avoid race conditions
        self.audio_input_queue: asyncio.Queue = asyncio.Queue()
        self.audio_output_queue: asyncio.Queue = asyncio.Queue()

        # Tasks
        self._response_task: Optional[asyncio.Task] = None
        self._audio_send_task: Optional[asyncio.Task] = None
        self._playback_task: Optional[asyncio.Task] = None

        # Session identifiers
        self.prompt_name: str = ""
        self.audio_content_name: str = ""

        # Transcript collection
        self.user_text_parts: list[str] = []
        self.assistant_text_parts: list[str] = []
        self._last_assistant_text: str = ""  # for dedup
        self.barge_in = False

        # PyAudio handles
        self._pa: Optional[pyaudio.PyAudio] = None
        self._input_stream = None
        self._output_stream = None

    # ── Client init ──────────────────────────────────────────────────────────
    def _init_bedrock(self) -> None:
        config = Config(
            endpoint_uri=f"https://bedrock-runtime.{self.region}.amazonaws.com",
            region=self.region,
            aws_credentials_identity_resolver=EnvironmentCredentialsResolver(),
            http_auth_scheme_resolver=HTTPAuthSchemeResolver(),
            http_auth_schemes={"aws.auth#sigv4": SigV4AuthScheme()},
        )
        self.bedrock_client = BedrockRuntimeClient(config=config)

    # ── Low-level send (lock-protected) ──────────────────────────────────────
    async def _send_event(self, payload: dict) -> None:
        raw = json.dumps(payload)
        chunk = InvokeModelWithBidirectionalStreamInputChunk(
            value=BidirectionalInputPayloadPart(bytes_=raw.encode("utf-8"))
        )
        async with self._send_lock:
            try:
                await self.stream.input_stream.send(chunk)
            except Exception as e:
                log_event(f"Send error: {e}")
                raise
        # Log non-audio events
        event_keys = list(payload.get("event", {}).keys())
        if "audioInput" not in event_keys and event_keys:
            log_event(f"SENT → {event_keys}")

    async def _send_json(self, raw_json: str) -> None:
        """Send a pre-serialized JSON string."""
        chunk = InvokeModelWithBidirectionalStreamInputChunk(
            value=BidirectionalInputPayloadPart(bytes_=raw_json.encode("utf-8"))
        )
        async with self._send_lock:
            await self.stream.input_stream.send(chunk)

    # ── Session lifecycle ────────────────────────────────────────────────────
    async def open_session(self, system_prompt: str) -> None:
        """Open stream, send sessionStart + promptStart + system text, start audio I/O."""
        if not self.bedrock_client:
            self._init_bedrock()

        self.stream = await self.bedrock_client.invoke_model_with_bidirectional_stream(
            InvokeModelWithBidirectionalStreamOperationInput(model_id=self.model_id)
        )
        self.is_active = True
        self.prompt_name = str(uuid.uuid4())
        self.audio_content_name = str(uuid.uuid4())
        self.user_text_parts.clear()
        self.assistant_text_parts.clear()
        self._last_assistant_text = ""
        self.barge_in = False

        # 1) sessionStart
        await self._send_event({
            "event": {
                "sessionStart": {
                    "inferenceConfiguration": {
                        "maxTokens": 1024,
                        "topP": 0.9,
                        "temperature": 0.1,
                    }
                }
            }
        })

        # 2) promptStart
        await self._send_event({
            "event": {
                "promptStart": {
                    "promptName": self.prompt_name,
                    "textOutputConfiguration": {"mediaType": "text/plain"},
                    "audioOutputConfiguration": {
                        "mediaType": "audio/lpcm",
                        "sampleRateHertz": OUTPUT_SAMPLE_RATE,
                        "sampleSizeBits": 16,
                        "channelCount": 1,
                        "voiceId": self.voice_id,
                        "encoding": "base64",
                        "audioType": "SPEECH",
                    },
                }
            }
        })

        # 3) System prompt as TEXT content
        sys_content = str(uuid.uuid4())
        await self._send_event({
            "event": {
                "contentStart": {
                    "promptName": self.prompt_name,
                    "contentName": sys_content,
                    "type": "TEXT",
                    "interactive": False,
                    "role": "SYSTEM",
                    "textInputConfiguration": {"mediaType": "text/plain"},
                }
            }
        })
        await self._send_event({
            "event": {
                "textInput": {
                    "promptName": self.prompt_name,
                    "contentName": sys_content,
                    "content": system_prompt,
                }
            }
        })
        await self._send_event({
            "event": {
                "contentEnd": {
                    "promptName": self.prompt_name,
                    "contentName": sys_content,
                }
            }
        })

        # 4) Open audio input content (stays open for mic streaming)
        await self._send_event({
            "event": {
                "contentStart": {
                    "promptName": self.prompt_name,
                    "contentName": self.audio_content_name,
                    "type": "AUDIO",
                    "interactive": True,
                    "role": "USER",
                    "audioInputConfiguration": {
                        "mediaType": "audio/lpcm",
                        "sampleRateHertz": INPUT_SAMPLE_RATE,
                        "sampleSizeBits": 16,
                        "channelCount": 1,
                        "audioType": "SPEECH",
                        "encoding": "base64",
                    },
                }
            }
        })

        # Start background tasks
        self._response_task = asyncio.create_task(self._response_loop())
        self._audio_send_task = asyncio.create_task(self._audio_send_loop())
        self._start_audio_io()

        log_info("Session opened")

    async def close_session(self) -> None:
        """Cleanly tear down: contentEnd → promptEnd → sessionEnd → close."""
        if not self.is_active:
            return
        self.is_active = False

        # Stop mic input stream first
        self._stop_audio_input()

        # Close audio content
        try:
            await self._send_event({
                "event": {
                    "contentEnd": {
                        "promptName": self.prompt_name,
                        "contentName": self.audio_content_name,
                    }
                }
            })
        except Exception:
            pass

        # promptEnd
        try:
            await self._send_event({
                "event": {"promptEnd": {"promptName": self.prompt_name}}
            })
        except Exception:
            pass

        # sessionEnd
        try:
            await self._send_event({"event": {"sessionEnd": {}}})
        except Exception:
            pass

        # Close the stream
        try:
            await self.stream.input_stream.close()
        except Exception:
            pass

        # Signal playback to stop
        await self.audio_output_queue.put(None)

        # Cancel tasks
        for task in [self._response_task, self._audio_send_task, self._playback_task]:
            if task and not task.done():
                task.cancel()
        tasks = [t for t in [self._response_task, self._audio_send_task, self._playback_task] if t]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        # Cleanup PyAudio output
        self._stop_audio_output()

        log_info("Session closed")


    # ── Send text instruction to model ───────────────────────────────────────
    async def send_text(self, text: str, role: str = "USER") -> None:
        """Send a text content block (USER or SYSTEM) within the current prompt."""
        cn = str(uuid.uuid4())
        await self._send_event({
            "event": {
                "contentStart": {
                    "promptName": self.prompt_name,
                    "contentName": cn,
                    "type": "TEXT",
                    "interactive": True,
                    "role": role,
                    "textInputConfiguration": {"mediaType": "text/plain"},
                }
            }
        })
        await self._send_event({
            "event": {
                "textInput": {
                    "promptName": self.prompt_name,
                    "contentName": cn,
                    "content": text,
                }
            }
        })
        await self._send_event({
            "event": {
                "contentEnd": {
                    "promptName": self.prompt_name,
                    "contentName": cn,
                }
            }
        })
        log_event(f"Sent text ({role}): {text[:80]}...")

    # ── Response processing loop ─────────────────────────────────────────────
    async def _response_loop(self) -> None:
        """Read events from the Bedrock stream and dispatch."""
        try:
            while self.is_active:
                try:
                    output = await self.stream.await_output()
                    result = await output[1].receive()
                    if not result.value or not result.value.bytes_:
                        continue
                    data = json.loads(result.value.bytes_.decode("utf-8"))
                    event = data.get("event", {})

                    if "contentStart" in event:
                        log_event(f"contentStart role={event['contentStart'].get('role')}")

                    elif "textOutput" in event:
                        to = event["textOutput"]
                        text = to.get("content", "")
                        role = to.get("role", "")

                        # Barge-in detection
                        if '{ "interrupted" : true }' in text:
                            self.barge_in = True
                            log_event("Barge-in detected")
                            continue

                        if role == "ASSISTANT" and text.strip():
                            # Deduplicate repeated outputs
                            if text.strip() != self._last_assistant_text:
                                self._last_assistant_text = text.strip()
                                self.assistant_text_parts.append(text.strip())
                                print(f"  🤖 {text.strip()}")
                        elif role == "USER" and text.strip():
                            self.user_text_parts.append(text.strip())
                            print(f"  🎤 {text.strip()}")

                    elif "audioOutput" in event:
                        audio_b64 = event["audioOutput"].get("content")
                        if audio_b64:
                            audio_bytes = base64.b64decode(audio_b64)
                            log_audio(f"audioOutput bytes={len(audio_bytes)}")
                            await self.audio_output_queue.put(audio_bytes)

                    elif "contentEnd" in event:
                        log_event("contentEnd")

                    elif "error" in event:
                        log_info(f"Stream error: {event['error']}")

                except StopAsyncIteration:
                    break
                except Exception as e:
                    if "ValidationException" in str(e):
                        log_info(f"Validation error: {e}")
                    else:
                        log_info(f"Response error: {e}")
                    break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log_info(f"Response loop fatal: {e}")
        finally:
            self.is_active = False

    # ── Audio send loop ──────────────────────────────────────────────────────
    async def _audio_send_loop(self) -> None:
        """Drain audio_input_queue and send audioInput events to Bedrock."""
        try:
            while self.is_active:
                try:
                    audio_bytes = await asyncio.wait_for(
                        self.audio_input_queue.get(), timeout=0.1
                    )
                except asyncio.TimeoutError:
                    continue
                if audio_bytes is None:
                    break
                blob = base64.b64encode(audio_bytes).decode("utf-8")
                await self._send_event({
                    "event": {
                        "audioInput": {
                            "promptName": self.prompt_name,
                            "contentName": self.audio_content_name,
                            "content": blob,
                        }
                    }
                })
        except asyncio.CancelledError:
            pass

    # ── PyAudio I/O ──────────────────────────────────────────────────────────
    def _start_audio_io(self) -> None:
        """Open mic input (callback-based) and speaker output streams."""
        self._pa = pyaudio.PyAudio()

        # Mic input with callback
        kwargs: dict[str, Any] = dict(
            format=FORMAT,
            channels=CHANNELS,
            rate=INPUT_SAMPLE_RATE,
            input=True,
            frames_per_buffer=CHUNK_SIZE,
            stream_callback=self._mic_callback,
        )
        if self.input_device_index is not None:
            kwargs["input_device_index"] = self.input_device_index
        self._input_stream = self._pa.open(**kwargs)

        # Speaker output (blocking write, driven from playback task)
        out_kwargs: dict[str, Any] = dict(
            format=FORMAT,
            channels=CHANNELS,
            rate=OUTPUT_SAMPLE_RATE,
            output=True,
            frames_per_buffer=CHUNK_SIZE,
        )
        if self.output_device_index is not None:
            out_kwargs["output_device_index"] = self.output_device_index
        self._output_stream = self._pa.open(**out_kwargs)

        # Start playback task
        self._playback_task = asyncio.create_task(self._playback_loop())

    def _mic_callback(self, in_data, frame_count, time_info, status):
        """PyAudio callback – push mic data into asyncio queue."""
        if self.is_active and in_data:
            try:
                self.audio_input_queue.put_nowait(in_data)
            except Exception:
                pass
        return (None, pyaudio.paContinue)

    def _stop_audio_input(self) -> None:
        if self._input_stream:
            try:
                if self._input_stream.is_active():
                    self._input_stream.stop_stream()
                self._input_stream.close()
            except Exception:
                pass
            self._input_stream = None

    def _stop_audio_output(self) -> None:
        if self._output_stream:
            try:
                if self._output_stream.is_active():
                    self._output_stream.stop_stream()
                self._output_stream.close()
            except Exception:
                pass
            self._output_stream = None
        if self._pa:
            try:
                self._pa.terminate()
            except Exception:
                pass
            self._pa = None

    async def _playback_loop(self) -> None:
        """Read from audio_output_queue and write to speaker."""
        loop = asyncio.get_event_loop()
        try:
            while True:
                data = await self.audio_output_queue.get()
                if data is None:
                    break
                # Handle barge-in: flush queue
                if self.barge_in:
                    while not self.audio_output_queue.empty():
                        try:
                            self.audio_output_queue.get_nowait()
                        except asyncio.QueueEmpty:
                            break
                    self.barge_in = False
                    continue
                if self._output_stream and not self._output_stream.is_stopped:
                    await loop.run_in_executor(None, self._output_stream.write, data)
        except asyncio.CancelledError:
            pass

    # ── High-level helpers for the state machine ─────────────────────────────
    def get_latest_user_text(self) -> str:
        """Return the most recent user transcript text and clear the buffer."""
        if self.user_text_parts:
            text = self.user_text_parts[-1]
            self.user_text_parts.clear()
            return text
        return ""

    def get_all_assistant_text(self) -> str:
        """Return all assistant text since last clear."""
        text = " ".join(self.assistant_text_parts)
        self.assistant_text_parts.clear()
        return text

    async def instruct_and_wait_for_speech(self, instruction: str, wait_s: float = 8.0) -> None:
        """Send a text instruction and wait for the model to finish speaking."""
        self.assistant_text_parts.clear()
        self.user_text_parts.clear()
        await self.send_text(instruction)
        # Wait for assistant to produce audio output
        await asyncio.sleep(wait_s)

    async def wait_for_user_response(self, timeout_s: float = 15.0, settle_s: float = 1.5) -> str:
        """Wait for user speech, with settle time after last transcript update."""
        self.user_text_parts.clear()
        deadline = asyncio.get_event_loop().time() + timeout_s
        last_update = 0.0
        latest = ""

        while asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(0.3)
            if self.user_text_parts:
                latest = self.user_text_parts[-1]
                last_update = asyncio.get_event_loop().time()
                self.user_text_parts.clear()
            elif latest and last_update and (asyncio.get_event_loop().time() - last_update) >= settle_s:
                return latest

        return latest


# ═══════════════════════════════════════════════════════════════════════════════
#  S3 Integration
# ═══════════════════════════════════════════════════════════════════════════════
class S3Uploader:
    """Pluggable S3 upload functions for cough WAV and final JSON."""

    def __init__(self, bucket: str, region: str):
        self.bucket = bucket
        self.s3 = boto3.client("s3", region_name=region)

    def upload_cough_wav(self, local_path: str) -> str:
        """Upload cough WAV file, return s3:// URI."""
        key = f"health-intake/cough/{uuid.uuid4()}.wav"
        self.s3.upload_file(local_path, self.bucket, key)
        uri = f"s3://{self.bucket}/{key}"
        log_info(f"Cough WAV uploaded → {uri}")
        return uri

    def upload_final_json(self, payload: dict) -> str:
        """Upload final JSON payload, return s3:// URI."""
        key = f"health-intake/json/{uuid.uuid4()}.json"
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.s3.put_object(Bucket=self.bucket, Key=key, Body=body, ContentType="application/json")
        uri = f"s3://{self.bucket}/{key}"
        log_info(f"Final JSON uploaded → {uri}")
        return uri


# ═══════════════════════════════════════════════════════════════════════════════
#  Cough Recording (offline, after Nova session ends)
# ═══════════════════════════════════════════════════════════════════════════════
def record_cough_wav(
    out_path: str,
    seconds: int = 8,
    input_device_index: Optional[int] = None,
) -> tuple[bool, int]:
    """
    Record cough audio to WAV. Returns (valid, burst_count).
    Validates via RMS threshold heuristic.
    """
    p = pyaudio.PyAudio()
    kwargs: dict[str, Any] = dict(
        format=FORMAT,
        channels=CHANNELS,
        rate=INPUT_SAMPLE_RATE,
        input=True,
        frames_per_buffer=CHUNK_SIZE,
    )
    if input_device_index is not None:
        kwargs["input_device_index"] = input_device_index

    stream = None
    try:
        stream = p.open(**kwargs)
        frames: list[bytes] = []
        rms_values: list[float] = []

        # Beep
        print("\a", end="", flush=True)
        log_info(f"Recording cough for {seconds}s... cough now!")

        total_chunks = int(INPUT_SAMPLE_RATE / CHUNK_SIZE * seconds)
        for _ in range(total_chunks):
            data = stream.read(CHUNK_SIZE, exception_on_overflow=False)
            frames.append(data)
            rms_values.append(pcm16_rms(data))

        # Write WAV
        with wave.open(out_path, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)
            wf.setframerate(INPUT_SAMPLE_RATE)
            wf.writeframes(b"".join(frames))

        log_info(f"Cough WAV saved: {out_path}")

        # Validate cough bursts
        valid, count = _validate_cough_bursts(rms_values)
        log_info(f"Cough validation: valid={valid}, bursts={count}")
        return valid, count

    finally:
        if stream:
            stream.stop_stream()
            stream.close()
        p.terminate()


def _validate_cough_bursts(rms_values: list[float]) -> tuple[bool, int]:
    """Heuristic: count RMS spikes above threshold as cough bursts."""
    if not rms_values:
        return False, 0
    peak = max(rms_values)
    median = sorted(rms_values)[len(rms_values) // 2]
    threshold = max(800.0, median * 2.5, peak * 0.4)

    count = 0
    cooldown = 0
    for v in rms_values:
        if cooldown > 0:
            cooldown -= 1
            continue
        if v >= threshold:
            count += 1
            cooldown = 8  # ~0.5s at 16kHz/1024 chunk

    return count >= 3, count


# ═══════════════════════════════════════════════════════════════════════════════
#  Health Intake Agent – Deterministic State Machine
# ═══════════════════════════════════════════════════════════════════════════════
class HealthIntakeAgent:
    """
    App-controlled turn-taking state machine.
    States: LANGUAGE_SELECT → ASKING → WAITING_USER → COUGH_PHASE → DONE
    Asks exactly one question at a time, waits for one answer, then advances.
    """

    # System prompt keeps the model tightly constrained
    SYSTEM_PROMPT = (
        "You are a multilingual health intake voice assistant. "
        "You MUST speak ONLY in the language the app tells you. "
        "You MUST say ONLY the exact sentence the app provides. "
        "Do NOT add extra sentences, greetings, or commentary. "
        "Do NOT diagnose or give medical advice. "
        "If told to speak Hindi, use natural Devanagari Hindi, not Hinglish. "
        "If told to speak English, use only English. "
        "Keep every response to one short sentence."
    )

    MAX_RETRIES = 2  # retries per question on timeout/no-input

    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.state = State.LANGUAGE_SELECT
        self.language: str = "English"  # default
        self.question_index: int = 0
        self.answers: dict[str, Any] = {}  # collected answers keyed by field name
        self.cough_s3_uri: str = ""

        self.nova = NovaSonicClient(
            model_id=args.model_id,
            region=args.region,
            voice_id=args.voice_id,
            input_device_index=args.input_device_index,
            output_device_index=args.output_device_index,
        )
        self.s3_uploader = S3Uploader(bucket=args.s3_bucket, region=args.region)

    # ── Build the final output JSON ──────────────────────────────────────────
    def _build_output(self) -> dict:
        """
        Build the exact output shape required:
        {"body": "{\"age\":50,\"gender\":\"M\",...}"}
        """
        body: dict[str, Any] = {}

        # Name
        body["name"] = self.answers.get("name", "")

        # Age
        age = self.answers.get("age")
        body["age"] = age if isinstance(age, int) else 0

        # Gender
        body["gender"] = self.answers.get("gender", "U")

        # Binary fields: strict 0/1
        for f in ALL_BINARY_FIELDS:
            val = self.answers.get(f)
            if val is None:
                body[f] = 0  # unknown → safe default
            else:
                body[f] = int(val) if isinstance(val, int) else 0

        # Cough S3 URI (extra, outside body string but useful)
        body_json_str = json.dumps(body, ensure_ascii=False)
        output = {"body": body_json_str}

        if self.cough_s3_uri:
            output["cough_audio_s3"] = self.cough_s3_uri

        return output

    # ── Speak a sentence via Nova ────────────────────────────────────────────
    async def _speak(self, english_text: str, hindi_text: str) -> None:
        """Instruct Nova to speak the appropriate language version."""
        if self.language == "Hindi":
            instruction = f"Speak in Hindi. Say exactly: {hindi_text}"
        else:
            instruction = f"Speak in English. Say exactly: {english_text}"
        await self.nova.instruct_and_wait_for_speech(instruction, wait_s=6.0)

    # ── Ask one question and get answer ──────────────────────────────────────
    async def _ask_one(self, q: IntakeQuestion) -> Optional[Any]:
        """
        Ask a single question, wait for user response.
        Returns parsed value or None (skip/timeout).
        Retries up to MAX_RETRIES on no-input.
        """
        for attempt in range(self.MAX_RETRIES + 1):
            self.state = State.ASKING

            # Instruct model to ask the question
            if self.language == "Hindi":
                instruction = f"Speak in Hindi. Ask exactly: {q.hindi}"
            else:
                instruction = f"Speak in English. Ask exactly: {q.english}"

            self.nova.assistant_text_parts.clear()
            self.nova.user_text_parts.clear()
            await self.nova.send_text(instruction)

            # Wait for model to speak the question
            await asyncio.sleep(5.0)

            # Now wait for user response
            self.state = State.WAITING_USER
            user_text = await self.nova.wait_for_user_response(timeout_s=12.0, settle_s=1.5)

            if not user_text.strip():
                if attempt < self.MAX_RETRIES:
                    log_info(f"No response for '{q.key}', retrying ({attempt + 1}/{self.MAX_RETRIES})...")
                    continue
                else:
                    log_info(f"No response for '{q.key}' after retries, using default.")
                    return None

            # Check skip
            if is_skip(user_text):
                log_info(f"User skipped '{q.key}'")
                return None

            # Parse based on field type
            if q.field_type == "binary":
                val = parse_binary(user_text)
                if val is not None:
                    return val
                # Unclear answer – use model to interpret
                val = await self._model_interpret_binary(user_text)
                return val

            elif q.field_type == "age":
                val = parse_age(user_text)
                if val is not None:
                    return val
                # Try model interpretation
                return await self._model_interpret_age(user_text)

            elif q.field_type == "gender":
                return parse_gender(user_text)

            else:  # text
                return user_text.strip()

        return None

    async def _model_interpret_binary(self, text: str) -> Optional[int]:
        """Ask the model to interpret an ambiguous yes/no answer."""
        instruction = (
            f"The user was asked a yes/no health question and answered: \"{text}\". "
            "Reply with ONLY the word 'yes' or 'no'. Nothing else."
        )
        await self.nova.send_text(instruction)
        await asyncio.sleep(3.0)
        response = self.nova.get_all_assistant_text().strip().lower()
        if "yes" in response:
            return 1
        if "no" in response:
            return 0
        return None

    async def _model_interpret_age(self, text: str) -> Optional[int]:
        """Ask the model to extract age from ambiguous text."""
        instruction = (
            f"The user was asked their age and answered: \"{text}\". "
            "Reply with ONLY the number. Nothing else."
        )
        await self.nova.send_text(instruction)
        await asyncio.sleep(3.0)
        response = self.nova.get_all_assistant_text().strip()
        return parse_age(response)

    # ── Language selection phase ──────────────────────────────────────────────
    async def _select_language(self) -> None:
        """Ask user to choose English or Hindi."""
        for attempt in range(self.MAX_RETRIES + 1):
            instruction = (
                "Speak in English. Say exactly: "
                "Please choose your language: English or Hindi?"
            )
            self.nova.assistant_text_parts.clear()
            self.nova.user_text_parts.clear()
            await self.nova.send_text(instruction)
            await asyncio.sleep(5.0)

            user_text = await self.nova.wait_for_user_response(timeout_s=10.0, settle_s=1.5)

            if user_text.strip():
                choice = detect_language_choice(user_text)
                if choice:
                    self.language = choice
                    log_info(f"Language selected: {self.language}")
                    # Confirm
                    if self.language == "Hindi":
                        await self._speak(
                            "You selected Hindi. Let us begin.",
                            "आपने हिंदी चुनी है। चलिए शुरू करते हैं।"
                        )
                    else:
                        await self._speak(
                            "You selected English. Let us begin.",
                            "You selected English. Let us begin."
                        )
                    return

            if attempt < self.MAX_RETRIES:
                log_info(f"Language not detected, retrying ({attempt + 1})...")
            else:
                log_info("Defaulting to English.")
                self.language = "English"

    # ── Cough phase ──────────────────────────────────────────────────────────
    async def _cough_phase(self) -> None:
        """Announce cough recording, close Nova session, record WAV, upload."""
        self.state = State.COUGH_PHASE

        # Speak the cough instruction
        await self._speak(
            "Now I will record your cough. Please cough three times after the beep.",
            "अब मैं आपकी खांसी रिकॉर्ड करूँगा। बीप के बाद कृपया तीन बार खांसें।"
        )

        # Wait for speech to finish playing
        await asyncio.sleep(2.0)

        # End Nova session cleanly BEFORE recording
        log_info("Closing Nova session for cough recording...")
        await self.nova.close_session()
        await asyncio.sleep(0.5)

        # Record cough WAV
        cough_path = "cough_recording.wav"
        cough_seconds = self.args.cough_seconds
        valid, burst_count = record_cough_wav(
            cough_path,
            seconds=cough_seconds,
            input_device_index=self.args.input_device_index,
        )
        log_info(f"Cough recording: valid={valid}, bursts={burst_count}")

        # Upload to S3
        self.cough_s3_uri = self.s3_uploader.upload_cough_wav(cough_path)

    # ── Main run loop ────────────────────────────────────────────────────────
    async def run(self) -> dict:
        """Execute the full intake flow. Returns the final output dict."""
        try:
            # Open Nova session
            await self.nova.open_session(self.SYSTEM_PROMPT)

            # 1) Language selection
            self.state = State.LANGUAGE_SELECT
            await self._select_language()

            # 2) Ask each intake question sequentially
            for i, q in enumerate(INTAKE_QUESTIONS):
                self.question_index = i
                log_info(f"Question {i + 1}/{len(INTAKE_QUESTIONS)}: {q.key}")
                value = await self._ask_one(q)
                self.answers[q.key] = value
                log_info(f"  → {q.key} = {value}")

            # 3) Cough phase
            await self._cough_phase()

            # 4) Thank the user (reopen session briefly)
            await self.nova.open_session(self.SYSTEM_PROMPT)
            await self._speak(
                "Thank you. Your health intake is complete.",
                "धन्यवाद। आपका स्वास्थ्य सेवन पूरा हो गया है।"
            )
            await asyncio.sleep(3.0)
            await self.nova.close_session()

            # 5) Build and upload final JSON
            self.state = State.DONE
            output = self._build_output()

            # Upload
            json_s3 = self.s3_uploader.upload_final_json(output)

            # Print
            print("\n" + "=" * 60)
            print("FINAL OUTPUT:")
            print("=" * 60)
            print(json.dumps(output, indent=2, ensure_ascii=False))
            print(f"\nJSON uploaded to: {json_s3}")
            print(f"Cough audio: {self.cough_s3_uri}")
            print("=" * 60)

            return output

        except KeyboardInterrupt:
            log_info("Interrupted by user")
            raise
        except Exception as e:
            log_info(f"Agent error: {e}")
            import traceback
            traceback.print_exc()
            raise
        finally:
            # Ensure cleanup
            try:
                await self.nova.close_session()
            except Exception:
                pass


# ═══════════════════════════════════════════════════════════════════════════════
#  CLI & Entry Point
# ═══════════════════════════════════════════════════════════════════════════════
def list_audio_devices() -> None:
    """Print all available audio devices."""
    p = pyaudio.PyAudio()
    try:
        n = p.get_device_count()
        print(f"\nDetected {n} audio device(s):\n")
        for i in range(n):
            info = p.get_device_info_by_index(i)
            name = info.get("name", "?")
            in_ch = int(info.get("maxInputChannels", 0))
            out_ch = int(info.get("maxOutputChannels", 0))
            sr = int(info.get("defaultSampleRate", 0))
            marker = ""
            if in_ch > 0 and out_ch > 0:
                marker = " [IN+OUT]"
            elif in_ch > 0:
                marker = " [IN]"
            elif out_ch > 0:
                marker = " [OUT]"
            print(f"  [{i}] {name}  in={in_ch} out={out_ch} sr={sr}{marker}")
        print()
    finally:
        p.terminate()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Nova 2 Sonic – Multilingual Health Intake Voice Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # macOS
  python nova_sonic_health_intake_agent.py --s3-bucket my-health-bucket --voice-id arjun

  # Windows
  python nova_sonic_health_intake_agent.py --s3-bucket my-health-bucket --voice-id arjun --input-device-index 1

  # List audio devices
  python nova_sonic_health_intake_agent.py --list-audio-devices --s3-bucket dummy

  # Debug mode
  python nova_sonic_health_intake_agent.py --s3-bucket my-bucket --debug-events --debug-audio
""",
    )
    parser.add_argument("--s3-bucket", required=True, help="S3 bucket for uploads (required)")
    parser.add_argument("--model-id", default="amazon.nova-2-sonic-v1:0", help="Bedrock model ID")
    parser.add_argument("--region", default=os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "us-east-1")),
                        help="AWS region (default: from env or us-east-1)")
    parser.add_argument("--voice-id", default="arjun", help="Nova Sonic voice ID (default: arjun)")
    parser.add_argument("--input-device-index", type=int, default=None, help="PyAudio input device index")
    parser.add_argument("--output-device-index", type=int, default=None, help="PyAudio output device index")
    parser.add_argument("--cough-seconds", type=int, default=8, help="Cough recording duration in seconds (default: 8)")
    parser.add_argument("--debug-events", action="store_true", help="Log all streaming events")
    parser.add_argument("--debug-audio", action="store_true", help="Log audio chunk details")
    parser.add_argument("--list-audio-devices", action="store_true", help="List audio devices and exit")
    return parser.parse_args()


async def async_main() -> None:
    args = parse_args()

    # Set debug flags
    global DEBUG_EVENTS, DEBUG_AUDIO
    DEBUG_EVENTS = args.debug_events
    DEBUG_AUDIO = args.debug_audio

    if args.list_audio_devices:
        list_audio_devices()
        return

    print()
    print("=" * 60)
    print("  Nova 2 Sonic – Health Intake Voice Agent")
    print(f"  Model:  {args.model_id}")
    print(f"  Region: {args.region}")
    print(f"  Voice:  {args.voice_id}")
    print(f"  Bucket: {args.s3_bucket}")
    print("=" * 60)
    print()

    agent = HealthIntakeAgent(args)
    await agent.run()


if __name__ == "__main__":
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("\nExiting.")
    except Exception as e:
        print(f"\nFatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
