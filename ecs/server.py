"""
Nova Sonic Health Intake Agent — ECS WebSocket Server
=====================================================
Standalone WebSocket server for ECS Fargate deployment.
Uses the same Bedrock streaming logic and conversation state machine
as the Lambda version, but with native WebSocket connections instead
of API Gateway + Lambda invocations.
"""

import asyncio
import base64
import json
import os
import struct
import math
import uuid
import signal
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from typing import Any, Optional

import boto3
import websockets

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
from smithy_core.aio.interfaces.identity import IdentityResolver
from smithy_aws_core.identity import AWSCredentialsIdentity

# ─── Environment ─────────────────────────────────────────────────────────────
S3_BUCKET = os.environ.get("S3_BUCKET", "")
BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-2-sonic-v1:0")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
VOICE_ID = os.environ.get("VOICE_ID", "arjun")
PORT = int(os.environ.get("PORT", "8080"))


# ─── Boto3-based credential resolver for ECS/EC2/env compatibility ───────────
class Boto3CredentialsResolver(IdentityResolver):
    """Resolves AWS credentials using boto3's credential chain.
    Works with ECS task roles, EC2 instance profiles, env vars, etc."""

    async def get_identity(self, *, properties=None):
        session = boto3.Session()
        creds = session.get_credentials()
        if creds is None:
            raise Exception("No AWS credentials found")
        frozen = creds.get_frozen_credentials()
        log_info(f"Credentials resolved: access_key={frozen.access_key[:8]}..., has_token={frozen.token is not None}")
        identity = AWSCredentialsIdentity(
            access_key_id=frozen.access_key,
            secret_access_key=frozen.secret_key,
        )
        if frozen.token:
            identity = AWSCredentialsIdentity(
                access_key_id=frozen.access_key,
                secret_access_key=frozen.secret_key,
                session_token=frozen.token,
            )
        return identity


def _refresh_env_credentials():
    """Populate AWS env vars from boto3 credential chain for SDK compatibility."""
    session = boto3.Session()
    creds = session.get_credentials()
    if creds:
        frozen = creds.get_frozen_credentials()
        os.environ["AWS_ACCESS_KEY_ID"] = frozen.access_key
        os.environ["AWS_SECRET_ACCESS_KEY"] = frozen.secret_key
        if frozen.token:
            os.environ["AWS_SESSION_TOKEN"] = frozen.token
        log_info(f"Env credentials set: {frozen.access_key[:8]}..., has_token={frozen.token is not None}")

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
    key: str
    english: str
    hindi: str
    field_type: str = "text"  # "text", "binary", "age", "gender"

INTAKE_QUESTIONS: list[IntakeQuestion] = [
    IntakeQuestion("name",   "What is your full name?", "आपका पूरा नाम क्या है?", "text"),
    IntakeQuestion("age",    "How old are you?", "आपकी उम्र क्या है?", "age"),
    IntakeQuestion("gender", "What is your gender? Male, Female, or Other?",
                   "आपका लिंग क्या है? पुरुष, महिला, या अन्य?", "gender"),
    IntakeQuestion("fever",   "Do you have fever? Yes or No.", "क्या आपको बुखार है? हाँ या नहीं।", "binary"),
    IntakeQuestion("cold",    "Do you have cold? Yes or No.", "क्या आपको सर्दी है? हाँ या नहीं।", "binary"),
    IntakeQuestion("cough",   "Do you have cough? Yes or No.", "क्या आपको खांसी है? हाँ या नहीं।", "binary"),
    IntakeQuestion("fatigue", "Do you have fatigue? Yes or No.", "क्या आपको थकान है? हाँ या नहीं।", "binary"),
    IntakeQuestion("loss_of_smell", "Have you lost your sense of smell? Yes or No.",
                   "क्या आपकी सूंघने की शक्ति कम हुई है? हाँ या नहीं।", "binary"),
    IntakeQuestion("breathing_difficulties", "Do you have breathing difficulties? Yes or No.",
                   "क्या आपको सांस लेने में कठिनाई है? हाँ या नहीं।", "binary"),
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
    t = text.strip().lower()
    tokens = set(t.split())
    if tokens & YES_WORDS or t in YES_WORDS:
        return 1
    if tokens & NO_WORDS or t in NO_WORDS:
        return 0
    for w in YES_WORDS:
        if w in t:
            return 1
    for w in NO_WORDS:
        if w in t:
            return 0
    return None


def parse_age(text: str) -> Optional[int]:
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
    t = text.strip().lower()
    if t in ("m", "f", "o"):
        return t.upper()
    for key, val in GENDER_MAP_ORDERED:
        if key in t:
            return val
    return "U"


def detect_language_choice(text: str) -> Optional[str]:
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


# ─── Logging ─────────────────────────────────────────────────────────────────
def ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

def log_info(msg: str) -> None:
    print(f"[{ts()}] {msg}", flush=True)


# ─── S3 Uploader ─────────────────────────────────────────────────────────────
class S3Uploader:
    def __init__(self, bucket: str, region: str):
        self.bucket = bucket
        self.s3 = boto3.client("s3", region_name=region)

    def upload_cough_wav(self, wav_bytes: bytes) -> str:
        key = f"health-intake/cough/{uuid.uuid4()}.wav"
        self.s3.put_object(Bucket=self.bucket, Key=key, Body=wav_bytes, ContentType="audio/wav")
        uri = f"s3://{self.bucket}/{key}"
        log_info(f"Cough WAV uploaded → {uri}")
        return uri

    def upload_final_json(self, payload: dict) -> str:
        key = f"health-intake/json/{uuid.uuid4()}.json"
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.s3.put_object(Bucket=self.bucket, Key=key, Body=body, ContentType="application/json")
        uri = f"s3://{self.bucket}/{key}"
        log_info(f"Final JSON uploaded → {uri}")
        return uri


# ─── BedrockStreamManager ────────────────────────────────────────────────────
class BedrockStreamManager:
    """
    Manages a bidirectional streaming session with Bedrock Nova Sonic.
    Sends audio/transcript directly to the client WebSocket instead of
    going through API Gateway Management API.
    """

    def __init__(self, model_id: str, region: str, voice_id: str, ws):
        self.model_id = model_id
        self.region = region
        self.voice_id = voice_id
        self.ws = ws  # websockets connection object

        self.bedrock_client: Optional[BedrockRuntimeClient] = None
        self.stream = None
        self.is_active = False

        self._send_lock = asyncio.Lock()
        self.audio_input_queue: asyncio.Queue = asyncio.Queue()

        self._response_task: Optional[asyncio.Task] = None
        self._audio_send_task: Optional[asyncio.Task] = None

        self.prompt_name: str = ""
        self.audio_content_name: str = ""

        self.user_text_parts: list[str] = []
        self.assistant_text_parts: list[str] = []
        self._last_assistant_text: str = ""
        self.barge_in = False
        self._mute_mic = False
        self._assistant_speaking = False
        self._assistant_audio_is_active = False
        self._audio_played_for_turn = False

    def _init_bedrock(self) -> None:
        # Refresh env credentials from task role before creating client
        _refresh_env_credentials()
        config = Config(
            endpoint_uri=f"https://bedrock-runtime.{self.region}.amazonaws.com",
            region=self.region,
            aws_credentials_identity_resolver=EnvironmentCredentialsResolver(),
            auth_schemes={"aws.auth#sigv4": SigV4AuthScheme(service="bedrock")},
        )
        self.bedrock_client = BedrockRuntimeClient(config=config)

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

    async def _send_to_client(self, message: dict) -> None:
        """Send JSON message to client via WebSocket."""
        try:
            await self.ws.send(json.dumps(message))
        except Exception as e:
            log_info(f"Failed to send to client: {e}")

    async def open_session(self, system_prompt: str) -> None:
        # Refresh credentials each session (ECS task role creds rotate)
        _refresh_env_credentials()
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

        while not self.audio_input_queue.empty():
            try:
                self.audio_input_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        await self._send_event({
            "event": {"sessionStart": {"inferenceConfiguration": {"maxTokens": 1024, "topP": 0.9, "temperature": 0.1}}}
        })
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

        sys_content = str(uuid.uuid4())
        await self._send_event({
            "event": {
                "contentStart": {
                    "promptName": self.prompt_name, "contentName": sys_content,
                    "type": "TEXT", "interactive": False, "role": "SYSTEM",
                    "textInputConfiguration": {"mediaType": "text/plain"},
                }
            }
        })
        await self._send_event({
            "event": {"textInput": {"promptName": self.prompt_name, "contentName": sys_content, "content": system_prompt}}
        })
        await self._send_event({
            "event": {"contentEnd": {"promptName": self.prompt_name, "contentName": sys_content}}
        })

        await self._send_event({
            "event": {
                "contentStart": {
                    "promptName": self.prompt_name, "contentName": self.audio_content_name,
                    "type": "AUDIO", "interactive": True, "role": "USER",
                    "audioInputConfiguration": {
                        "mediaType": "audio/lpcm", "sampleRateHertz": INPUT_SAMPLE_RATE,
                        "sampleSizeBits": 16, "channelCount": 1, "audioType": "SPEECH", "encoding": "base64",
                    },
                }
            }
        })

        self._response_task = asyncio.create_task(self._response_loop())
        self._audio_send_task = asyncio.create_task(self._audio_send_loop())
        log_info("Bedrock session opened")

    async def close_session(self) -> None:
        if not self.is_active:
            return
        self.is_active = False
        try:
            await self._send_event({"event": {"contentEnd": {"promptName": self.prompt_name, "contentName": self.audio_content_name}}})
        except Exception:
            pass
        try:
            await self._send_event({"event": {"promptEnd": {"promptName": self.prompt_name}}})
        except Exception:
            pass
        try:
            await self._send_event({"event": {"sessionEnd": {}}})
        except Exception:
            pass
        try:
            await self.stream.input_stream.close()
        except Exception:
            pass
        await asyncio.sleep(0.3)
        for task in [self._response_task, self._audio_send_task]:
            if task and not task.done():
                task.cancel()
        tasks = [t for t in [self._response_task, self._audio_send_task] if t]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        log_info("Bedrock session closed")

    async def send_text(self, text: str, role: str = "USER") -> None:
        self._audio_played_for_turn = False
        self._assistant_audio_is_active = False
        cn = str(uuid.uuid4())
        await self._send_event({
            "event": {"contentStart": {
                "promptName": self.prompt_name, "contentName": cn,
                "type": "TEXT", "interactive": True, "role": role,
                "textInputConfiguration": {"mediaType": "text/plain"},
            }}
        })
        await self._send_event({
            "event": {"textInput": {"promptName": self.prompt_name, "contentName": cn, "content": text}}
        })
        await self._send_event({
            "event": {"contentEnd": {"promptName": self.prompt_name, "contentName": cn}}
        })
        log_info(f"Sent text ({role}): {text[:80]}...")

    async def _response_loop(self) -> None:
        log_info("_response_loop STARTED")
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
                        if '{ "interrupted" : true }' in text:
                            self.barge_in = True
                            log_info("Barge-in detected")
                            continue
                        if role == "ASSISTANT" and text.strip():
                            if text.strip() != self._last_assistant_text:
                                self._last_assistant_text = text.strip()
                                self.assistant_text_parts.append(text.strip())
                                await self._send_to_client({"type": "transcript", "role": "assistant", "text": text.strip()})
                        elif role == "USER" and text.strip():
                            self.user_text_parts.append(text.strip())
                            await self._send_to_client({"type": "transcript", "role": "user", "text": text.strip()})

                    elif "audioOutput" in event:
                        audio_b64 = event["audioOutput"].get("content")
                        if audio_b64 and not self._audio_played_for_turn:
                            await self._send_to_client({"type": "audio", "data": audio_b64})

                    elif "contentEnd" in event:
                        if self._assistant_audio_is_active:
                            self._audio_played_for_turn = True
                            self._assistant_audio_is_active = False
                        self._assistant_speaking = False
                        log_info(f"contentEnd (audio_played={self._audio_played_for_turn})")

                    elif "error" in event:
                        log_info(f"Stream error: {event['error']}")

                    else:
                        log_info(f"Unknown Bedrock event: {list(event.keys())}")

                except StopAsyncIteration:
                    log_info("_response_loop: StopAsyncIteration — stream ended")
                    break
                except Exception as e:
                    log_info(f"_response_loop inner error: {type(e).__name__}: {e}")
                    import traceback
                    traceback.print_exc()
                    break
        except asyncio.CancelledError:
            log_info("_response_loop CANCELLED")
        except Exception as e:
            log_info(f"_response_loop FATAL: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
        finally:
            log_info("_response_loop EXITED")
            self.is_active = False

    async def _audio_send_loop(self) -> None:
        """Drain audio_input_queue and send audioInput events to Bedrock.
        CRITICAL: Bedrock requires continuous audio input to keep the stream alive.
        Send silence when no real audio is available."""
        try:
            while self.is_active:
                try:
                    audio_bytes = await asyncio.wait_for(self.audio_input_queue.get(), timeout=0.1)
                except asyncio.TimeoutError:
                    # Always send silence to keep the Bedrock stream alive
                    silence = b"\x00" * 1024
                    blob = base64.b64encode(silence).decode("utf-8")
                    await self._send_event({
                        "event": {"audioInput": {
                            "promptName": self.prompt_name, "contentName": self.audio_content_name, "content": blob,
                        }}
                    })
                    continue
                if audio_bytes is None:
                    break
                if self._mute_mic:
                    audio_bytes = b"\x00" * len(audio_bytes)
                blob = base64.b64encode(audio_bytes).decode("utf-8")
                await self._send_event({
                    "event": {"audioInput": {
                        "promptName": self.prompt_name, "contentName": self.audio_content_name, "content": blob,
                    }}
                })
        except asyncio.CancelledError:
            pass

    def get_all_assistant_text(self) -> str:
        text = " ".join(self.assistant_text_parts)
        self.assistant_text_parts.clear()
        return text

    async def instruct_and_wait_for_speech(self, instruction: str, wait_s: float = 10.0) -> None:
        self.assistant_text_parts.clear()
        self.user_text_parts.clear()
        await self.send_text(instruction)
        deadline = asyncio.get_event_loop().time() + wait_s
        while asyncio.get_event_loop().time() < deadline:
            if self._audio_played_for_turn:
                await asyncio.sleep(0.15)
                return
            await asyncio.sleep(0.05)

    async def wait_for_user_response(self, timeout_s: float = 10.0, settle_s: float = 1.0,
                                     quick_answers: bool = False) -> str:
        self.user_text_parts.clear()
        deadline = asyncio.get_event_loop().time() + timeout_s
        last_update = 0.0
        latest = ""
        while asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(0.1)
            if self.user_text_parts:
                latest = self.user_text_parts[-1]
                last_update = asyncio.get_event_loop().time()
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


# ─── ConversationManager ─────────────────────────────────────────────────────
class ConversationManager:
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

    def __init__(self, ws):
        self.ws = ws
        self.state = State.LANGUAGE_SELECT
        self.language: str = "English"
        self.question_index: int = 0
        self.answers: dict[str, Any] = {}
        self.cough_s3_uri: str = ""
        self._cough_future: Optional[asyncio.Future] = None

        self.nova = BedrockStreamManager(
            model_id=BEDROCK_MODEL_ID, region=AWS_REGION, voice_id=VOICE_ID, ws=ws,
        )
        self.s3_uploader = S3Uploader(bucket=S3_BUCKET, region=AWS_REGION)

    async def _send_to_client(self, message: dict) -> None:
        try:
            await self.ws.send(json.dumps(message))
        except Exception as e:
            log_info(f"Failed to send to client: {e}")

    async def _send_state_update(self, question: Optional[str] = None) -> None:
        await self._send_to_client({"type": "state", "state": self.state.name, "question": question})

    async def _wait_until_assistant_done(self, timeout_s: float = 10.0) -> None:
        deadline = asyncio.get_event_loop().time() + timeout_s
        while asyncio.get_event_loop().time() < deadline:
            if self.nova._audio_played_for_turn:
                await asyncio.sleep(0.15)
                return
            await asyncio.sleep(0.05)

    async def _speak(self, english_text: str, hindi_text: str) -> None:
        if self.language == "Hindi":
            instruction = f"Speak in Hindi. Say exactly: {hindi_text}"
        else:
            instruction = f"Speak in English. Say exactly: {english_text}"
        self.nova._mute_mic = True
        await self.nova.instruct_and_wait_for_speech(instruction, wait_s=8.0)
        self.nova._mute_mic = False

    async def _select_language(self) -> None:
        await self._send_state_update()
        for attempt in range(self.MAX_RETRIES + 1):
            instruction = "Speak in English. Say exactly and ONLY: Please choose your language: English or Hindi?"
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
                    # Close and reopen session to prevent model from adding commentary
                    await self.nova.close_session()
                    await asyncio.sleep(0.3)
                    await self.nova.open_session(self.SYSTEM_PROMPT)
                    if self.language == "Hindi":
                        await self._speak("You selected Hindi. Let us begin.", "आपने हिंदी चुनी है। चलिए शुरू करते हैं।")
                    else:
                        await self._speak("You selected English. Let us begin.", "You selected English. Let us begin.")
                    return
            if attempt < self.MAX_RETRIES:
                log_info(f"Language not detected, retrying ({attempt + 1})...")
            else:
                log_info("Defaulting to English.")
                self.language = "English"

    async def _ask_one(self, q: IntakeQuestion) -> Optional[Any]:
        for attempt in range(self.MAX_RETRIES + 1):
            self.state = State.ASKING
            await self._send_state_update(question=q.key)
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
            await self._send_state_update(question=q.key)
            is_quick = q.field_type == "binary"
            user_text = await self.nova.wait_for_user_response(
                timeout_s=8.0, settle_s=0.15 if is_quick else 0.4, quick_answers=is_quick,
            )
            if not user_text.strip():
                if attempt < self.MAX_RETRIES:
                    log_info(f"No response for '{q.key}', retrying ({attempt + 1}/{self.MAX_RETRIES})...")
                    continue
                else:
                    return None
            if is_skip(user_text):
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
            else:
                return user_text.strip()
        return None

    async def _model_interpret_binary(self, text: str) -> Optional[int]:
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
        instruction = (
            f'The user said: "{text}". Extract the age as a number. '
            "Respond with ONLY the number, nothing else."
        )
        self.nova._mute_mic = True
        await self.nova.send_text(instruction)
        await self._wait_until_assistant_done(timeout_s=5.0)
        self.nova._mute_mic = False
        response = self.nova.get_all_assistant_text().strip()
        return parse_age(response)

    def _build_output(self) -> dict:
        body: dict[str, Any] = {}
        body["name"] = self.answers.get("name", "")
        body["age"] = self.answers.get("age") if isinstance(self.answers.get("age"), int) else 0
        body["gender"] = self.answers.get("gender", "U")
        for f in ALL_BINARY_FIELDS:
            val = self.answers.get(f)
            body[f] = int(val) if isinstance(val, int) else 0
        body_json_str = json.dumps(body, ensure_ascii=False)
        output = {"body": body_json_str}
        if self.cough_s3_uri:
            output["cough_audio_s3"] = self.cough_s3_uri
        return output

    async def _cough_phase(self) -> None:
        self.state = State.COUGH_PHASE
        await self._send_state_update()
        await self._speak(
            "Now I will record your cough. Please cough three times after the beep.",
            "अब मैं आपकी खांसी रिकॉर्ड करूँगा। बीप के बाद कृपया तीन बार खांसें।",
        )
        await asyncio.sleep(2.0)
        log_info("Closing Nova session for cough recording...")
        await self.nova.close_session()
        await asyncio.sleep(0.5)
        self._cough_future = asyncio.get_event_loop().create_future()
        await self._send_to_client({"type": "cough_start", "duration": self.COUGH_DURATION})
        try:
            cough_wav_bytes = await asyncio.wait_for(self._cough_future, timeout=30.0)
        except asyncio.TimeoutError:
            log_info("Cough recording timed out")
            cough_wav_bytes = None
        finally:
            self._cough_future = None
        if cough_wav_bytes:
            self.cough_s3_uri = self.s3_uploader.upload_cough_wav(cough_wav_bytes)
        else:
            log_info("No cough audio received, skipping upload")

    def receive_cough_audio(self, data_b64: str) -> None:
        if self._cough_future and not self._cough_future.done():
            try:
                wav_bytes = base64.b64decode(data_b64)
                self._cough_future.set_result(wav_bytes)
            except Exception as e:
                self._cough_future.set_exception(e)

    async def run(self) -> dict:
        try:
            await self.nova.open_session(self.SYSTEM_PROMPT)
            self.state = State.LANGUAGE_SELECT
            await self._select_language()
            for i, q in enumerate(INTAKE_QUESTIONS):
                self.question_index = i
                log_info(f"Question {i + 1}/{len(INTAKE_QUESTIONS)}: {q.key}")
                value = await self._ask_one(q)
                self.answers[q.key] = value
                log_info(f"  → {q.key} = {value}")
            await self._cough_phase()
            await self.nova.open_session(self.SYSTEM_PROMPT)
            await self._speak(
                "Thank you. Your health intake is complete.",
                "धन्यवाद। आपका स्वास्थ्य सेवन पूरा हो गया है।",
            )
            await asyncio.sleep(3.0)
            await self.nova.close_session()
            self.state = State.DONE
            output = self._build_output()
            json_s3 = self.s3_uploader.upload_final_json(output)
            log_info(f"Final JSON uploaded: {json_s3}")
            await self._send_to_client({"type": "result", "data": output})
            await self._send_state_update()
            return output
        except Exception as e:
            log_info(f"ConversationManager error: {e}")
            import traceback
            traceback.print_exc()
            await self._send_to_client({"type": "error", "message": str(e)})
            raise
        finally:
            try:
                await self.nova.close_session()
            except Exception:
                pass


# ─── WebSocket Handler ───────────────────────────────────────────────────────
async def handle_connection(ws):
    """Handle a single WebSocket client connection."""
    remote = ws.remote_address
    log_info(f"Client connected: {remote}")

    conv_mgr = ConversationManager(ws)
    conversation_task: Optional[asyncio.Task] = None

    try:
        async for raw_message in ws:
            try:
                message = json.loads(raw_message)
            except (json.JSONDecodeError, TypeError):
                log_info(f"Invalid JSON from {remote}")
                continue

            msg_type = message.get("type", "")
            log_info(f"Received message type: {msg_type} from {remote}")

            if msg_type == "control":
                action = message.get("action", "")
                log_info(f"Control action: {action}")
                if action == "start":
                    if conversation_task and not conversation_task.done():
                        log_info("Conversation already running")
                        continue
                    conversation_task = asyncio.create_task(conv_mgr.run())
                else:
                    await ws.send(json.dumps({"type": "error", "message": f"Unknown action: {action}"}))

            elif msg_type == "audio":
                data = message.get("data", "")
                if data and conv_mgr.nova.is_active:
                    audio_bytes = base64.b64decode(data)
                    try:
                        conv_mgr.nova.audio_input_queue.put_nowait(audio_bytes)
                    except Exception:
                        pass

            elif msg_type == "cough_audio":
                data = message.get("data", "")
                if data:
                    conv_mgr.receive_cough_audio(data)

            else:
                log_info(f"Unknown message type: {msg_type}")

    except websockets.exceptions.ConnectionClosed as e:
        log_info(f"Client disconnected: {remote} (code={e.code})")
    except Exception as e:
        log_info(f"Connection error for {remote}: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if conversation_task and not conversation_task.done():
            conversation_task.cancel()
            try:
                await conversation_task
            except (asyncio.CancelledError, Exception):
                pass
        try:
            await conv_mgr.nova.close_session()
        except Exception:
            pass
        log_info(f"Cleaned up: {remote}")


# ─── Main ────────────────────────────────────────────────────────────────────
async def main():
    log_info(f"Starting WebSocket server on port {PORT}")

    stop = asyncio.get_event_loop().create_future()

    def _signal_handler():
        if not stop.done():
            stop.set_result(True)

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _signal_handler)

    # Health check handler for ECS — responds to plain HTTP with 200
    async def health_check(path, request_headers):
        if path == "/health":
            return (200, [], b"OK\n")
        return None

    async with websockets.serve(
        handle_connection, "0.0.0.0", PORT,
        process_request=health_check,
        ping_interval=30,
        ping_timeout=10,
    ):
        log_info(f"Server listening on ws://0.0.0.0:{PORT}")
        await stop

    log_info("Server shutting down")


if __name__ == "__main__":
    asyncio.run(main())
