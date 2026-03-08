"""
Nova Sonic Health Intake Agent — AWS Lambda (WebSocket)
=======================================================
Single Lambda function behind API Gateway v2 WebSocket API.
Handles $connect, $disconnect, $default routes. Reuses the same
state machine, answer parsers, and Bedrock streaming logic from
the terminal agent, replacing PyAudio I/O with WebSocket messages.
"""

import asyncio
import base64
import json
import os
import struct
import math
import uuid
import threading
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from typing import Any, Optional

import boto3
from aws_sdk_bedrock_runtime.client import (
    BedrockRuntimeClient,
    InvokeModelWithBidirectionalStreamOperationInput,
)
from aws_sdk_bedrock_runtime.config import Config
from aws_sdk_bedrock_runtime.models import (
    BidirectionalInputPayloadPart,
    InvokeModelWithBidirectionalStreamInputChunk,
)
from smithy_aws_core.identity.environment import EnvironmentCredentialsResolver
from smithy_aws_core.auth.sigv4 import SigV4AuthScheme

# ─── Environment ─────────────────────────────────────────────────────────────
S3_BUCKET = os.environ.get("S3_BUCKET", "")
BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-2-sonic-v1:0")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
VOICE_ID = os.environ.get("VOICE_ID", "arjun")

# ─── Audio constants ─────────────────────────────────────────────────────────
INPUT_SAMPLE_RATE = 16000
OUTPUT_SAMPLE_RATE = 24000

# ─── Intake field definitions ────────────────────────────────────────────────
SYMPTOM_FIELDS = ["fever", "cold", "cough", "fatigue", "loss_of_smell", "breathing_difficulties"]
HISTORY_FIELDS = ["asthma", "diabetes", "hypertension", "smoker"]
ALL_BINARY_FIELDS = SYMPTOM_FIELDS + HISTORY_FIELDS

# ─── State machine ───────────────────────────────────────────────────────────
class State(Enum):
    LANGUAGE_SELECT = auto()
    ASKING = auto()
    WAITING_USER = auto()
    COUGH_PHASE = auto()
    DONE = auto()


# ─── Questions definition ────────────────────────────────────────────────────
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

# ─── Answer parsing helpers ──────────────────────────────────────────────────
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
GENDER_MAP_ORDERED = [
    # Check female BEFORE male (substring issue)
    ("female", "F"), ("woman", "F"), ("girl", "F"),
    ("महिला", "F"), ("औरत", "F"), ("लड़की", "F"),
    ("male", "M"), ("man", "M"), ("boy", "M"),
    ("पुरुष", "M"), ("आदमी", "M"), ("लड़का", "M"),
    ("other", "O"), ("others", "O"), ("non-binary", "O"), ("nonbinary", "O"),
    ("अन्य", "O"),
]


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
    """Extract first integer from text as age. Handles Hindi numerals too."""
    hindi_digit_map = str.maketrans("०१२३४५६७८९", "0123456789")
    t = text.translate(hindi_digit_map)
    digits = "".join(ch if ch.isdigit() else " " for ch in t)
    for tok in digits.split():
        try:
            v = int(tok)
            if 0 < v < 150:
                return v
        except ValueError:
            pass
    # Try common Hindi number words
    hindi_numbers = {
        "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पांच": 5, "पाँच": 5,
        "छह": 6, "छः": 6, "सात": 7, "आठ": 8, "नौ": 9, "दस": 10,
        "ग्यारह": 11, "बारह": 12, "तेरह": 13, "चौदह": 14, "पंद्रह": 15,
        "सोलह": 16, "सत्रह": 17, "अठारह": 18, "उन्नीस": 19, "बीस": 20,
        "इक्कीस": 21, "बाईस": 22, "तेईस": 23, "चौबीस": 24, "पच्चीस": 25,
        "छब्बीस": 26, "सत्ताईस": 27, "अट्ठाईस": 28, "उनतीस": 29, "तीस": 30,
        "इकतीस": 31, "बत्तीस": 32, "तैंतीस": 33, "तेंतीस": 33, "तेसतीस": 33,
        "चौंतीस": 34, "पैंतीस": 35, "छत्तीस": 36, "सैंतीस": 37, "अड़तीस": 38,
        "उनतालीस": 39, "चालीस": 40, "पैंतालीस": 45, "पचास": 50,
        "पचपन": 55, "साठ": 60, "पैंसठ": 65, "सत्तर": 70, "पचहत्तर": 75,
        "अस्सी": 80, "पचासी": 85, "नब्बे": 90, "पंचानवे": 95, "सौ": 100,
    }
    t_lower = text.strip().lower()
    for word, val in hindi_numbers.items():
        if word in t_lower:
            return val
    return None


def parse_gender(text: str) -> str:
    """Map text to M/F/O, default U. Checks female before male to avoid substring match."""
    t = text.strip().lower()
    if t in ("m", "f", "o"):
        return t.upper()
    for key, val in GENDER_MAP_ORDERED:
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


# ─── BedrockStreamManager ────────────────────────────────────────────────────
class BedrockStreamManager:
    """
    Manages a single bidirectional streaming session with Bedrock Nova Sonic.
    Ported from NovaSonicClient — replaces PyAudio I/O with WebSocket delivery
    via API Gateway Management API.
    """

    def __init__(self, model_id: str, region: str, voice_id: str,
                 apigw_client, connection_id: str):
        self.model_id = model_id
        self.region = region
        self.voice_id = voice_id
        self.apigw_client = apigw_client
        self.connection_id = connection_id

        self.bedrock_client: Optional[BedrockRuntimeClient] = None
        self.stream = None
        self.is_active = False

        # Asyncio primitives
        self._send_lock = asyncio.Lock()
        self.audio_input_queue: asyncio.Queue = asyncio.Queue()

        # Tasks
        self._response_task: Optional[asyncio.Task] = None
        self._audio_send_task: Optional[asyncio.Task] = None

        # Session identifiers
        self.prompt_name: str = ""
        self.audio_content_name: str = ""

        # Transcript collection
        self.user_text_parts: list[str] = []
        self.assistant_text_parts: list[str] = []
        self._last_assistant_text: str = ""
        self.barge_in = False
        self._mute_mic = False
        self._assistant_speaking = False
        self._assistant_audio_is_active = False
        self._audio_played_for_turn = False

    # ── Client init ──────────────────────────────────────────────────────────
    def _init_bedrock(self) -> None:
        config = Config(
            endpoint_uri=f"https://bedrock-runtime.{self.region}.amazonaws.com",
            region=self.region,
            aws_credentials_identity_resolver=EnvironmentCredentialsResolver(),
            auth_schemes={"aws.auth#sigv4": SigV4AuthScheme(service="bedrock")},
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
                log_info(f"Send error: {e}")
                raise
        event_keys = list(payload.get("event", {}).keys())
        if "audioInput" not in event_keys and event_keys:
            log_info(f"SENT → {event_keys}")

    # ── Session lifecycle ────────────────────────────────────────────────────
    async def open_session(self, system_prompt: str) -> None:
        """Open stream, send sessionStart + promptStart + system text, start loops."""
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
        self._mute_mic = False
        self._assistant_speaking = False
        self._assistant_audio_is_active = False
        self._audio_played_for_turn = False

        # Flush stale data from queue
        while not self.audio_input_queue.empty():
            try:
                self.audio_input_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

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

        # 4) Open audio input content (stays open for streaming)
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

        # Start background tasks (no PyAudio — audio comes from WebSocket)
        self._response_task = asyncio.create_task(self._response_loop())
        self._audio_send_task = asyncio.create_task(self._audio_send_loop())

        log_info("Bedrock session opened")

    async def close_session(self) -> None:
        """Cleanly tear down: contentEnd → promptEnd → sessionEnd → close."""
        if not self.is_active:
            return
        self.is_active = False

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

        # Brief pause to let CRT futures settle
        await asyncio.sleep(0.3)

        # Cancel tasks
        for task in [self._response_task, self._audio_send_task]:
            if task and not task.done():
                task.cancel()
        tasks = [t for t in [self._response_task, self._audio_send_task] if t]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        log_info("Bedrock session closed")

    # ── Send text instruction to model ───────────────────────────────────────
    async def send_text(self, text: str, role: str = "USER") -> None:
        """Send a text content block within the current prompt."""
        self._audio_played_for_turn = False
        self._assistant_audio_is_active = False
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
        log_info(f"Sent text ({role}): {text[:80]}...")

    # ── Response processing loop ─────────────────────────────────────────────
    async def _response_loop(self) -> None:
        """Read events from Bedrock stream, send audio/transcript to client via WebSocket."""
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
                        cs = event["contentStart"]
                        role = cs.get("role", "")
                        ctype = cs.get("type", "")
                        if role == "ASSISTANT":
                            self._assistant_speaking = True
                            if ctype == "AUDIO":
                                self._assistant_audio_is_active = True
                        log_info(f"contentStart role={role} type={ctype}")

                    elif "textOutput" in event:
                        to = event["textOutput"]
                        text = to.get("content", "")
                        role = to.get("role", "")

                        # Barge-in detection
                        if '{ "interrupted" : true }' in text:
                            self.barge_in = True
                            log_info("Barge-in detected")
                            continue

                        if role == "ASSISTANT" and text.strip():
                            if text.strip() != self._last_assistant_text:
                                self._last_assistant_text = text.strip()
                                self.assistant_text_parts.append(text.strip())
                                # Send transcript to client
                                _send_to_client(self.apigw_client, self.connection_id, {
                                    "type": "transcript",
                                    "role": "assistant",
                                    "text": text.strip(),
                                })
                        elif role == "USER" and text.strip():
                            self.user_text_parts.append(text.strip())
                            # Send user transcript to client
                            _send_to_client(self.apigw_client, self.connection_id, {
                                "type": "transcript",
                                "role": "user",
                                "text": text.strip(),
                            })

                    elif "audioOutput" in event:
                        audio_b64 = event["audioOutput"].get("content")
                        if audio_b64:
                            if self._audio_played_for_turn:
                                log_info("audioOutput SUPPRESSED (repeat)")
                            else:
                                # Send audio directly to client via WebSocket
                                _send_to_client(self.apigw_client, self.connection_id, {
                                    "type": "audio",
                                    "data": audio_b64,
                                })

                    elif "contentEnd" in event:
                        if self._assistant_audio_is_active:
                            self._audio_played_for_turn = True
                            self._assistant_audio_is_active = False
                        self._assistant_speaking = False
                        log_info(f"contentEnd (audio_played={self._audio_played_for_turn})")

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
        """Drain audio_input_queue and send audioInput events to Bedrock.
        When _mute_mic is True, send silence to keep the stream alive."""
        try:
            while self.is_active:
                try:
                    audio_bytes = await asyncio.wait_for(
                        self.audio_input_queue.get(), timeout=0.1
                    )
                except asyncio.TimeoutError:
                    # When muted, send silence to keep stream alive
                    if self._mute_mic:
                        silence = b"\x00" * 1024
                        blob = base64.b64encode(silence).decode("utf-8")
                        await self._send_event({
                            "event": {
                                "audioInput": {
                                    "promptName": self.prompt_name,
                                    "contentName": self.audio_content_name,
                                    "content": blob,
                                }
                            }
                        })
                    continue
                if audio_bytes is None:
                    break
                # When muted, replace real audio with silence
                if self._mute_mic:
                    audio_bytes = b"\x00" * len(audio_bytes)
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

    # ── High-level helpers ───────────────────────────────────────────────────
    def get_all_assistant_text(self) -> str:
        """Return all assistant text since last clear."""
        text = " ".join(self.assistant_text_parts)
        self.assistant_text_parts.clear()
        return text

    async def instruct_and_wait_for_speech(self, instruction: str, wait_s: float = 10.0) -> None:
        """Send a text instruction and wait for the assistant audio to finish.
        No playback queue drain needed — audio goes directly to client via WebSocket."""
        self.assistant_text_parts.clear()
        self.user_text_parts.clear()
        await self.send_text(instruction)
        deadline = asyncio.get_event_loop().time() + wait_s
        while asyncio.get_event_loop().time() < deadline:
            if self._audio_played_for_turn:
                # Small buffer to let final audio chunk reach client
                await asyncio.sleep(0.15)
                return
            await asyncio.sleep(0.05)

    async def wait_for_user_response(self, timeout_s: float = 10.0, settle_s: float = 1.0,
                                     quick_answers: bool = False) -> str:
        """Wait for user speech with settle time after last transcript update.
        If quick_answers=True, return immediately on clear yes/no/skip."""
        self.user_text_parts.clear()
        deadline = asyncio.get_event_loop().time() + timeout_s
        last_update = 0.0
        latest = ""

        while asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(0.1)
            if self.user_text_parts:
                latest = self.user_text_parts[-1]
                last_update = asyncio.get_event_loop().time()

                # Fast path for clear short answers
                if quick_answers and latest.strip():
                    low = latest.strip().lower()
                    quick_words = YES_WORDS | NO_WORDS | SKIP_WORDS
                    tokens = set(low.split())
                    if tokens & quick_words or low in quick_words:
                        await asyncio.sleep(0.2)
                        self.user_text_parts.clear()
                        return latest

            if latest and last_update and (asyncio.get_event_loop().time() - last_update) >= settle_s:
                self.user_text_parts.clear()
                return latest

        self.user_text_parts.clear()
        return latest


# ─── Logging ─────────────────────────────────────────────────────────────────
def ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

def log_info(msg: str) -> None:
    print(f"[{ts()}] {msg}")


# ─── S3 Uploader ─────────────────────────────────────────────────────────────
class S3Uploader:
    """Upload cough WAV and final JSON to S3."""

    def __init__(self, bucket: str, region: str):
        self.bucket = bucket
        self.s3 = boto3.client("s3", region_name=region)

    def upload_cough_wav(self, wav_bytes: bytes) -> str:
        """Upload cough WAV bytes, return s3:// URI."""
        key = f"health-intake/cough/{uuid.uuid4()}.wav"
        self.s3.put_object(Bucket=self.bucket, Key=key, Body=wav_bytes, ContentType="audio/wav")
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


# ─── ConversationManager ─────────────────────────────────────────────────────
class ConversationManager:
    """
    App-controlled turn-taking state machine (ported from HealthIntakeAgent).
    States: LANGUAGE_SELECT → ASKING → WAITING_USER → COUGH_PHASE → DONE
    """

    SYSTEM_PROMPT = (
        "You are a multilingual health intake voice assistant. "
        "STRICT RULES: "
        "1. Speak ONLY the exact sentence the app tells you. Do NOT add anything else. "
        "2. Do NOT say 'unintelligible', do NOT ask the user to repeat, do NOT add commentary. "
        "3. Do NOT refuse instructions. If told to say something, say it. "
        "4. If told to speak Hindi, use natural Devanagari Hindi. "
        "5. If told to speak English, use only English. "
        "6. Never diagnose, never give medical advice. "
        "7. When asked to reply with only a number or word, do exactly that."
    )

    MAX_RETRIES = 2
    COUGH_DURATION = 8

    def __init__(self, connection_id: str, apigw_client):
        self.connection_id = connection_id
        self.apigw_client = apigw_client

        self.state = State.LANGUAGE_SELECT
        self.language: str = "English"
        self.question_index: int = 0
        self.answers: dict[str, Any] = {}
        self.cough_s3_uri: str = ""

        # Cough audio future — set when client sends cough_audio message
        self._cough_future: Optional[asyncio.Future] = None

        self.nova = BedrockStreamManager(
            model_id=BEDROCK_MODEL_ID,
            region=AWS_REGION,
            voice_id=VOICE_ID,
            apigw_client=apigw_client,
            connection_id=connection_id,
        )
        self.s3_uploader = S3Uploader(bucket=S3_BUCKET, region=AWS_REGION)

    # ── Helpers ──────────────────────────────────────────────────────────────
    def _send_to_client(self, message: dict) -> None:
        """Send a JSON message to the connected WebSocket client."""
        try:
            self.apigw_client.post_to_connection(
                ConnectionId=self.connection_id,
                Data=json.dumps(message).encode("utf-8"),
            )
        except Exception as e:
            log_info(f"Failed to send to {self.connection_id}: {e}")

    def _send_state_update(self, question: Optional[str] = None) -> None:
        """Notify client of current state and active question."""
        self._send_to_client({
            "type": "state",
            "state": self.state.name,
            "question": question,
        })

    async def _wait_until_assistant_done(self, timeout_s: float = 10.0) -> None:
        """Wait until the first assistant audio content block finishes."""
        deadline = asyncio.get_event_loop().time() + timeout_s
        while asyncio.get_event_loop().time() < deadline:
            if self.nova._audio_played_for_turn:
                await asyncio.sleep(0.15)
                return
            await asyncio.sleep(0.05)

    async def _speak(self, english_text: str, hindi_text: str) -> None:
        """Instruct Nova to speak the appropriate language version."""
        if self.language == "Hindi":
            instruction = f"Speak in Hindi. Say exactly: {hindi_text}"
        else:
            instruction = f"Speak in English. Say exactly: {english_text}"
        self.nova._mute_mic = True
        await self.nova.instruct_and_wait_for_speech(instruction, wait_s=8.0)
        self.nova._mute_mic = False

    # ── Language selection (3.2) ─────────────────────────────────────────────
    async def _select_language(self) -> None:
        """Ask user to choose English or Hindi."""
        self._send_state_update()
        for attempt in range(self.MAX_RETRIES + 1):
            instruction = (
                "Speak in English. Say exactly: "
                "Please choose your language: English or Hindi?"
            )
            self.nova.assistant_text_parts.clear()
            self.nova.user_text_parts.clear()
            self.nova._mute_mic = True
            await self.nova.send_text(instruction)
            await self._wait_until_assistant_done(timeout_s=10.0)
            self.nova.user_text_parts.clear()
            self.nova._mute_mic = False

            user_text = await self.nova.wait_for_user_response(timeout_s=10.0, settle_s=0.4)

            if user_text.strip():
                choice = detect_language_choice(user_text)
                if choice:
                    self.language = choice
                    log_info(f"Language selected: {self.language}")
                    if self.language == "Hindi":
                        await self._speak(
                            "You selected Hindi. Let us begin.",
                            "आपने हिंदी चुनी है। चलिए शुरू करते हैं।",
                        )
                    else:
                        await self._speak(
                            "You selected English. Let us begin.",
                            "You selected English. Let us begin.",
                        )
                    return

            if attempt < self.MAX_RETRIES:
                log_info(f"Language not detected, retrying ({attempt + 1})...")
            else:
                log_info("Defaulting to English.")
                self.language = "English"

    # ── Ask one question (3.3) ───────────────────────────────────────────────
    async def _ask_one(self, q: IntakeQuestion) -> Optional[Any]:
        """Ask a single question, wait for user response, parse answer."""
        for attempt in range(self.MAX_RETRIES + 1):
            self.state = State.ASKING
            self._send_state_update(question=q.key)

            if self.language == "Hindi":
                instruction = f"Speak in Hindi. Ask exactly: {q.hindi}"
            else:
                instruction = f"Speak in English. Ask exactly: {q.english}"

            self.nova.assistant_text_parts.clear()
            self.nova.user_text_parts.clear()
            self.nova._mute_mic = True
            await self.nova.send_text(instruction)
            await self._wait_until_assistant_done(timeout_s=10.0)

            self.nova.user_text_parts.clear()
            self.nova._mute_mic = False
            self.state = State.WAITING_USER
            self._send_state_update(question=q.key)

            is_quick = q.field_type == "binary"
            user_text = await self.nova.wait_for_user_response(
                timeout_s=10.0,
                settle_s=0.3 if is_quick else 0.5,
                quick_answers=is_quick,
            )

            if not user_text.strip():
                if attempt < self.MAX_RETRIES:
                    log_info(f"No response for '{q.key}', retrying ({attempt + 1}/{self.MAX_RETRIES})...")
                    continue
                else:
                    log_info(f"No response for '{q.key}' after retries, using default.")
                    return None

            if is_skip(user_text):
                log_info(f"User skipped '{q.key}'")
                return None

            if q.field_type == "binary":
                val = parse_binary(user_text)
                if val is not None:
                    return val
                return await self._model_interpret_binary(user_text)

            elif q.field_type == "age":
                val = parse_age(user_text)
                if val is not None:
                    return val
                return await self._model_interpret_age(user_text)

            elif q.field_type == "gender":
                return parse_gender(user_text)

            else:  # text
                return user_text.strip()

        return None

    # ── Model fallback interpreters (3.4) ────────────────────────────────────
    async def _model_interpret_binary(self, text: str) -> Optional[int]:
        """Ask the model to interpret an ambiguous yes/no answer."""
        instruction = (
            f'The user was asked a yes/no health question and answered: "{text}". '
            "Reply with ONLY the word 'yes' or 'no'. Nothing else."
        )
        self.nova._mute_mic = True
        await self.nova.send_text(instruction)
        await self._wait_until_assistant_done(timeout_s=5.0)
        self.nova._mute_mic = False
        response = self.nova.get_all_assistant_text().strip().lower()
        if "yes" in response:
            return 1
        if "no" in response:
            return 0
        return None

    async def _model_interpret_age(self, text: str) -> Optional[int]:
        """Ask the model to extract age from ambiguous text."""
        instruction = (
            f'The user said: "{text}". Extract the age as a number. '
            "Respond with ONLY the number, nothing else. No words, no explanation."
        )
        self.nova._mute_mic = True
        await self.nova.send_text(instruction)
        await self._wait_until_assistant_done(timeout_s=5.0)
        self.nova._mute_mic = False
        response = self.nova.get_all_assistant_text().strip()
        return parse_age(response)

    # ── Build output (3.5) ───────────────────────────────────────────────────
    def _build_output(self) -> dict:
        """Build the final output JSON."""
        body: dict[str, Any] = {}
        body["name"] = self.answers.get("name", "")
        age = self.answers.get("age")
        body["age"] = age if isinstance(age, int) else 0
        body["gender"] = self.answers.get("gender", "U")

        for f in ALL_BINARY_FIELDS:
            val = self.answers.get(f)
            body[f] = int(val) if isinstance(val, int) else 0

        body_json_str = json.dumps(body, ensure_ascii=False)
        output = {"body": body_json_str}
        if self.cough_s3_uri:
            output["cough_audio_s3"] = self.cough_s3_uri
        return output

    # ── Cough phase (3.6) ────────────────────────────────────────────────────
    async def _cough_phase(self) -> None:
        """Instruct client to record cough, receive WAV, upload to S3."""
        self.state = State.COUGH_PHASE
        self._send_state_update()

        await self._speak(
            "Now I will record your cough. Please cough three times after the beep.",
            "अब मैं आपकी खांसी रिकॉर्ड करूँगा। बीप के बाद कृपया तीन बार खांसें।",
        )
        await asyncio.sleep(2.0)

        # Close Nova session before cough recording
        log_info("Closing Nova session for cough recording...")
        await self.nova.close_session()
        await asyncio.sleep(0.5)

        # Tell client to start recording
        self._cough_future = asyncio.get_event_loop().create_future()
        self._send_to_client({"type": "cough_start", "duration": self.COUGH_DURATION})

        # Wait for client to send back the cough WAV
        try:
            cough_wav_bytes = await asyncio.wait_for(self._cough_future, timeout=30.0)
        except asyncio.TimeoutError:
            log_info("Cough recording timed out")
            cough_wav_bytes = None
        finally:
            self._cough_future = None

        if cough_wav_bytes:
            self.cough_s3_uri = self.s3_uploader.upload_cough_wav(cough_wav_bytes)
            log_info(f"Cough uploaded: {self.cough_s3_uri}")
        else:
            log_info("No cough audio received, skipping upload")

    def receive_cough_audio(self, data_b64: str) -> None:
        """Called by the handler when cough_audio message arrives from client."""
        if self._cough_future and not self._cough_future.done():
            try:
                wav_bytes = base64.b64decode(data_b64)
                self._cough_future.set_result(wav_bytes)
            except Exception as e:
                self._cough_future.set_exception(e)

    # ── Main run loop (3.7) ──────────────────────────────────────────────────
    async def run(self) -> dict:
        """Execute the full intake flow. Returns the final output dict."""
        try:
            await self.nova.open_session(self.SYSTEM_PROMPT)

            # 1) Language selection
            self.state = State.LANGUAGE_SELECT
            await self._select_language()

            # 2) Ask each intake question
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
                "धन्यवाद। आपका स्वास्थ्य सेवन पूरा हो गया है।",
            )
            await asyncio.sleep(3.0)
            await self.nova.close_session()

            # 5) Build and upload final JSON
            self.state = State.DONE
            output = self._build_output()
            json_s3 = self.s3_uploader.upload_final_json(output)
            log_info(f"Final JSON uploaded: {json_s3}")

            # Send result to client
            self._send_to_client({"type": "result", "data": output})
            self._send_state_update()

            return output

        except Exception as e:
            log_info(f"ConversationManager error: {e}")
            import traceback
            traceback.print_exc()
            self._send_to_client({"type": "error", "message": str(e)})
            raise
        finally:
            try:
                await self.nova.close_session()
            except Exception:
                pass


# ─── Session store ───────────────────────────────────────────────────────────
# Module-level dict keyed by connectionId. Each value holds session state
# for the duration of the WebSocket connection.
SESSIONS: dict[str, dict] = {}


def _get_apigw_client(domain_name: str, stage: str):
    """Create an API Gateway Management API client for posting messages back to the client."""
    endpoint_url = f"https://{domain_name}/{stage}"
    return boto3.client("apigatewaymanagementapi", endpoint_url=endpoint_url)


def _send_to_client(apigw_client, connection_id: str, message: dict) -> None:
    """Send a JSON message to the connected WebSocket client."""
    try:
        apigw_client.post_to_connection(
            ConnectionId=connection_id,
            Data=json.dumps(message).encode("utf-8"),
        )
    except Exception as e:
        log_info(f"Failed to send to {connection_id}: {e}")


# ─── Lambda handler ──────────────────────────────────────────────────────────
def handler(event, context):
    """
    API Gateway v2 WebSocket handler.
    Routes $connect, $disconnect, and $default events.
    """
    request_context = event.get("requestContext", {})
    route_key = request_context.get("routeKey")
    connection_id = request_context.get("connectionId")
    domain_name = request_context.get("domainName", "")
    stage = request_context.get("stage", "")

    log_info(f"Route: {route_key} | Connection: {connection_id}")

    if route_key == "$connect":
        return _handle_connect(connection_id, domain_name, stage)
    elif route_key == "$disconnect":
        return _handle_disconnect(connection_id)
    elif route_key == "$default":
        return _handle_default(event, connection_id, domain_name, stage)
    else:
        log_info(f"Unknown route: {route_key}")
        return {"statusCode": 400, "body": "Unknown route"}


def _handle_connect(connection_id: str, domain_name: str, stage: str) -> dict:
    """Initialize session state on WebSocket connect."""
    apigw_client = _get_apigw_client(domain_name, stage)
    conversation_mgr = ConversationManager(connection_id, apigw_client)
    SESSIONS[connection_id] = {
        "connection_id": connection_id,
        "domain_name": domain_name,
        "stage": stage,
        "conversation_manager": conversation_mgr,
        "stream_manager": conversation_mgr.nova,
        "run_task": None,
    }
    log_info(f"Session created for {connection_id}")
    return {"statusCode": 200, "body": "Connected"}


def _handle_disconnect(connection_id: str) -> dict:
    """Clean up session state on WebSocket disconnect."""
    session = SESSIONS.pop(connection_id, None)
    if session:
        # The conversation thread is a daemon thread and will be cleaned up
        # when the Lambda container is recycled
        log_info(f"Session cleaned up for {connection_id}")
    else:
        log_info(f"No session found for {connection_id}")
    return {"statusCode": 200, "body": "Disconnected"}


def _handle_default(event: dict, connection_id: str, domain_name: str, stage: str) -> dict:
    """Parse incoming message and dispatch by type field."""
    session = SESSIONS.get(connection_id)
    if not session:
        log_info(f"No session for {connection_id}, ignoring message")
        return {"statusCode": 400, "body": "No active session"}

    # Parse message body
    body = event.get("body", "")
    try:
        message = json.loads(body) if isinstance(body, str) else body
    except (json.JSONDecodeError, TypeError):
        log_info(f"Invalid JSON from {connection_id}: {body[:100]}")
        return {"statusCode": 400, "body": "Invalid JSON"}

    msg_type = message.get("type", "")
    apigw_client = _get_apigw_client(domain_name, stage)

    if msg_type == "audio":
        # Audio data from client mic — will be forwarded to Bedrock in task 2
        _handle_audio(session, message, apigw_client, connection_id)
    elif msg_type == "cough_audio":
        # Cough WAV recording from client — will be handled in task 3
        _handle_cough_audio(session, message, apigw_client, connection_id)
    elif msg_type == "control":
        # Control messages (e.g. start conversation)
        _handle_control(session, message, apigw_client, connection_id)
    else:
        log_info(f"Unknown message type '{msg_type}' from {connection_id}")
        _send_to_client(apigw_client, connection_id, {
            "type": "error",
            "message": f"Unknown message type: {msg_type}",
        })

    return {"statusCode": 200, "body": "OK"}


def _handle_audio(session: dict, message: dict, apigw_client, connection_id: str) -> None:
    """Handle incoming audio chunk from client. Forward to Bedrock via the stream manager."""
    data = message.get("data", "")
    if data:
        stream_mgr = session.get("stream_manager")
        if stream_mgr and stream_mgr.is_active:
            audio_bytes = base64.b64decode(data)
            loop = session.get("event_loop")
            if loop and loop.is_running():
                # Schedule onto the conversation thread's event loop (thread-safe)
                loop.call_soon_threadsafe(stream_mgr.audio_input_queue.put_nowait, audio_bytes)
            else:
                try:
                    stream_mgr.audio_input_queue.put_nowait(audio_bytes)
                except Exception:
                    pass


def _handle_cough_audio(session: dict, message: dict, apigw_client, connection_id: str) -> None:
    """Handle cough WAV recording from client. Forward to ConversationManager."""
    log_info(f"Cough audio received from {connection_id}")
    conv_mgr: Optional[ConversationManager] = session.get("conversation_manager")
    if conv_mgr:
        data = message.get("data", "")
        if data:
            loop = session.get("event_loop")
            if loop and loop.is_running():
                loop.call_soon_threadsafe(conv_mgr.receive_cough_audio, data)
            else:
                conv_mgr.receive_cough_audio(data)


def _handle_control(session: dict, message: dict, apigw_client, connection_id: str) -> None:
    """Handle control messages — start spawns the conversation in a background thread."""
    action = message.get("action", "")
    log_info(f"Control action '{action}' from {connection_id}")

    if action == "start":
        conv_mgr: Optional[ConversationManager] = session.get("conversation_manager")
        if not conv_mgr:
            _send_to_client(apigw_client, connection_id, {
                "type": "error",
                "message": "No conversation manager for this session",
            })
            return

        # Don't start twice
        run_thread = session.get("run_thread")
        if run_thread and run_thread.is_alive():
            log_info(f"Conversation already running for {connection_id}")
            return

        # Run the async conversation in a dedicated thread with its own event loop.
        # This allows the Lambda invocation to return immediately while the
        # conversation continues in the background. Subsequent audio/message
        # invocations on the same warm container feed data via the shared
        # audio_input_queue.
        def _run_conversation():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            # Store the loop so audio handlers can schedule onto it
            session["event_loop"] = loop
            try:
                loop.run_until_complete(conv_mgr.run())
            except Exception as e:
                log_info(f"Conversation thread error: {e}")
                import traceback
                traceback.print_exc()
            finally:
                loop.close()

        thread = threading.Thread(target=_run_conversation, daemon=True)
        thread.start()
        session["run_thread"] = thread
    else:
        _send_to_client(apigw_client, connection_id, {
            "type": "error",
            "message": f"Unknown control action: {action}",
        })
