#!/usr/bin/env python3
"""
Nova 2 Sonic Health Intake Agent (single-script terminal app)

Requirements (pip):
  pip install pyaudio boto3 aws-sdk-bedrock-runtime smithy-aws-core
"""

import argparse
import asyncio
import base64
import json
import math
import os
import struct
import time
import uuid
import wave
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import boto3
import pyaudio
from aws_sdk_bedrock_runtime.client import (
    BedrockRuntimeClient,
    InvokeModelWithBidirectionalStreamOperationInput,
)
from aws_sdk_bedrock_runtime.config import Config
from aws_sdk_bedrock_runtime.models import (
    BidirectionalInputPayloadPart,
    InvokeModelWithBidirectionalStreamInputChunk,
)
from smithy_aws_core.identity import StaticCredentialsResolver

INPUT_SAMPLE_RATE = 16000
OUTPUT_SAMPLE_RATE = 24000
CHANNELS = 1
FORMAT = pyaudio.paInt16
CHUNK_SIZE = 1024


HEALTH_SYSTEM_PROMPT = (
    "You are a multilingual health intake agent. Ask one question at a time in the "
    "selected language. Adapt based on answers. Collect structured information. "
    "The user picks either English or Hindi. If user mixes languages, still respond only "
    "in selected language. If selected language is Hindi, speak natural Hindi in Devanagari "
    "script and avoid Hinglish unless user explicitly asks. If selected language is English, "
    "speak neutral English only. Be calm and professional. If user says 'skip', acknowledge and "
    "move on. Do not diagnose. Do not provide risk score. Do not give medical advice."
)


def pcm16_rms(data: bytes) -> int:
    if not data:
        return 0
    sample_count = len(data) // 2
    if sample_count == 0:
        return 0
    samples = struct.unpack("<" + ("h" * sample_count), data[: sample_count * 2])
    mean_sq = sum(s * s for s in samples) / sample_count
    return int(math.sqrt(mean_sq))


@dataclass
class PromptResult:
    prompt_name: str
    assistant_text: str
    user_text: str


class NovaSonicBidiClient:
    def __init__(
        self,
        model_id: str,
        region: str,
        voice_id: str,
        debug_events: bool = False,
        debug_audio: bool = False,
        input_device_index: Optional[int] = None,
        output_device_index: Optional[int] = None,
    ):
        self.model_id = model_id
        self.region = region
        self.voice_id = voice_id
        self.debug_events = debug_events
        self.debug_audio = debug_audio
        self.input_device_index = input_device_index
        self.output_device_index = output_device_index

        self.client: Optional[BedrockRuntimeClient] = None
        self.stream = None
        self.is_active = False

        self.response_task: Optional[asyncio.Task] = None
        self.playback_task: Optional[asyncio.Task] = None
        self.mic_task: Optional[asyncio.Task] = None

        self.session_prompt_name: Optional[str] = None
        self.audio_input_content_name: Optional[str] = None

        self.audio_out_queue: asyncio.Queue[Optional[bytes]] = asyncio.Queue()
        self.user_text_queue: asyncio.Queue[str] = asyncio.Queue()
        self.assistant_text_queue: asyncio.Queue[str] = asyncio.Queue()
        self.capture_enabled = False

        self.events: list[dict[str, Any]] = []
        self.events_cv = asyncio.Condition()
        self.content_roles: dict[tuple[str, str], str] = {}
        self._last_user_text = ""
        self.transcript: list[dict[str, str]] = []

    def _initialize_client(self) -> None:
        session = boto3.Session(region_name=self.region)
        creds = session.get_credentials()
        if creds is None:
            raise RuntimeError("No AWS credentials found. Configure credentials or AWS_PROFILE.")
        frozen = creds.get_frozen_credentials()

        config = Config(
            endpoint_uri=f"https://bedrock-runtime.{self.region}.amazonaws.com",
            region=self.region,
            aws_credentials_identity_resolver=StaticCredentialsResolver(),
            aws_access_key_id=frozen.access_key,
            aws_secret_access_key=frozen.secret_key,
            aws_session_token=frozen.token,
        )
        self.client = BedrockRuntimeClient(config=config)

    async def _send_event(self, payload: dict[str, Any]) -> None:
        event_json = json.dumps(payload, ensure_ascii=True)
        event = InvokeModelWithBidirectionalStreamInputChunk(
            value=BidirectionalInputPayloadPart(bytes_=event_json.encode("utf-8"))
        )
        await self.stream.input_stream.send(event)

    def _audio_output_config(self) -> dict[str, Any]:
        return {
            "mediaType": "audio/lpcm",
            "sampleRateHertz": OUTPUT_SAMPLE_RATE,
            "sampleSizeBits": 16,
            "channelCount": 1,
            "voiceId": self.voice_id,
            "encoding": "base64",
            "audioType": "SPEECH",
        }

    def _audio_input_config(self) -> dict[str, Any]:
        return {
            "mediaType": "audio/lpcm",
            "sampleRateHertz": INPUT_SAMPLE_RATE,
            "sampleSizeBits": 16,
            "channelCount": 1,
            "audioType": "SPEECH",
            "encoding": "base64",
        }

    async def _append_event(self, event: dict[str, Any]) -> None:
        async with self.events_cv:
            self.events.append(event)
            self.events_cv.notify_all()

    def _event_mark(self) -> int:
        return len(self.events)

    async def _wait_for(self, predicate, since_mark: int, timeout_s: float) -> list[dict[str, Any]]:
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout_s
        cursor = since_mark
        matched: list[dict[str, Any]] = []

        while True:
            async with self.events_cv:
                new_events = self.events[cursor:]
                cursor = len(self.events)
                for ev in new_events:
                    if predicate(ev):
                        matched.append(ev)

                if loop.time() >= deadline:
                    return matched

                wait_left = deadline - loop.time()
                try:
                    await asyncio.wait_for(self.events_cv.wait(), timeout=wait_left)
                except asyncio.TimeoutError:
                    return matched

    async def _send_system_content(self, prompt_name: str, system_text: str) -> None:
        content_name = str(uuid.uuid4())
        await self._send_event(
            {
                "event": {
                    "contentStart": {
                        "promptName": prompt_name,
                        "contentName": content_name,
                        "type": "TEXT",
                        "interactive": False,
                        "role": "SYSTEM",
                        "textInputConfiguration": {"mediaType": "text/plain"},
                    }
                }
            }
        )
        await self._send_event(
            {
                "event": {
                    "textInput": {
                        "promptName": prompt_name,
                        "contentName": content_name,
                        "content": system_text,
                    }
                }
            }
        )
        await self._send_event(
            {
                "event": {
                    "contentEnd": {
                        "promptName": prompt_name,
                        "contentName": content_name,
                    }
                }
            }
        )

    async def _send_user_text(self, text: str) -> None:
        if not self.session_prompt_name:
            raise RuntimeError("Session prompt not initialized")
        content_name = str(uuid.uuid4())
        await self._send_event(
            {
                "event": {
                    "contentStart": {
                        "promptName": self.session_prompt_name,
                        "contentName": content_name,
                        "type": "TEXT",
                        "interactive": True,
                        "role": "USER",
                        "textInputConfiguration": {"mediaType": "text/plain"},
                    }
                }
            }
        )
        await self._send_event(
            {
                "event": {
                    "textInput": {
                        "promptName": self.session_prompt_name,
                        "contentName": content_name,
                        "content": text,
                    }
                }
            }
        )
        await self._send_event(
            {
                "event": {
                    "contentEnd": {
                        "promptName": self.session_prompt_name,
                        "contentName": content_name,
                    }
                }
            }
        )

    async def _start_continuous_audio_input(self) -> None:
        if not self.session_prompt_name:
            raise RuntimeError("Session prompt not initialized")

        self.audio_input_content_name = str(uuid.uuid4())
        await self._send_event(
            {
                "event": {
                    "contentStart": {
                        "promptName": self.session_prompt_name,
                        "contentName": self.audio_input_content_name,
                        "type": "AUDIO",
                        "interactive": True,
                        "role": "USER",
                        "audioInputConfiguration": self._audio_input_config(),
                    }
                }
            }
        )
        self.mic_task = asyncio.create_task(self._mic_capture_loop())

    async def _stop_continuous_audio_input(self) -> None:
        if self.mic_task and not self.mic_task.done():
            self.mic_task.cancel()
            await asyncio.gather(self.mic_task, return_exceptions=True)
        self.mic_task = None

        if self.session_prompt_name and self.audio_input_content_name:
            await self._send_event(
                {
                    "event": {
                        "contentEnd": {
                            "promptName": self.session_prompt_name,
                            "contentName": self.audio_input_content_name,
                        }
                    }
                }
            )
        self.audio_input_content_name = None

    async def _mic_capture_loop(self) -> None:
        p = pyaudio.PyAudio()
        stream = p.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=INPUT_SAMPLE_RATE,
            input=True,
            frames_per_buffer=CHUNK_SIZE,
            input_device_index=self.input_device_index,
        )
        silent_chunk = b"\x00\x00" * CHUNK_SIZE
        try:
            while self.is_active and self.session_prompt_name and self.audio_input_content_name:
                data = stream.read(CHUNK_SIZE, exception_on_overflow=False)
                if not self.capture_enabled:
                    data = silent_chunk
                blob = base64.b64encode(data).decode("utf-8")
                await self._send_event(
                    {
                        "event": {
                            "audioInput": {
                                "promptName": self.session_prompt_name,
                                "contentName": self.audio_input_content_name,
                                "content": blob,
                            }
                        }
                    }
                )
        except asyncio.CancelledError:
            pass
        finally:
            stream.stop_stream()
            stream.close()
            p.terminate()

    async def start_session(self, system_prompt: str) -> None:
        if not self.client:
            self._initialize_client()

        self.stream = await self.client.invoke_model_with_bidirectional_stream(
            InvokeModelWithBidirectionalStreamOperationInput(model_id=self.model_id)
        )
        self.is_active = True

        self.response_task = asyncio.create_task(self._process_responses())
        self.playback_task = asyncio.create_task(self._play_audio())

        await self._send_event(
            {
                "event": {
                    "sessionStart": {
                        "inferenceConfiguration": {
                            "maxTokens": 1024,
                            "topP": 0.9,
                            "temperature": 0.2,
                        }
                    }
                }
            }
        )

        self.session_prompt_name = str(uuid.uuid4())
        await self._send_event(
            {
                "event": {
                    "promptStart": {
                        "promptName": self.session_prompt_name,
                        "textOutputConfiguration": {"mediaType": "text/plain"},
                        "audioOutputConfiguration": self._audio_output_config(),
                    }
                }
            }
        )

        await self._send_system_content(self.session_prompt_name, system_prompt)
        await self._start_continuous_audio_input()
        self.capture_enabled = True

    async def end_session(self) -> None:
        if not self.is_active:
            return

        self.is_active = False
        self.capture_enabled = False
        await self._stop_continuous_audio_input()

        if self.session_prompt_name:
            await self._send_event(
                {"event": {"promptEnd": {"promptName": self.session_prompt_name}}}
            )
        await self._send_event({"event": {"sessionEnd": {}}})
        await self.stream.input_stream.close()

        self.session_prompt_name = None
        await self.audio_out_queue.put(None)

        tasks = [t for t in [self.response_task, self.playback_task] if t]
        if tasks:
            done, pending = await asyncio.wait(tasks, timeout=2.0)
            for t in pending:
                t.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

    async def _process_responses(self) -> None:
        try:
            while self.is_active:
                output = await self.stream.await_output()
                result = await output[1].receive()
                if not result.value or not result.value.bytes_:
                    continue

                payload = json.loads(result.value.bytes_.decode("utf-8"))
                event = payload.get("event", {})
                if self.debug_events and event:
                    print(f"[Event] {', '.join(event.keys())}")

                if "contentStart" in event:
                    cs = event["contentStart"]
                    p = cs.get("promptName", "")
                    c = cs.get("contentName", "")
                    r = cs.get("role", "")
                    if p and c and r:
                        self.content_roles[(p, c)] = r
                    await self._append_event(
                        {
                            "type": "contentStart",
                            "promptName": p,
                            "contentName": c,
                            "role": r,
                        }
                    )

                elif "textOutput" in event:
                    to = event["textOutput"]
                    p = to.get("promptName", "")
                    c = to.get("contentName", "")
                    text = to.get("content", "")
                    role = to.get("role") or self.content_roles.get((p, c), "UNKNOWN")
                    await self._append_event(
                        {
                            "type": "textOutput",
                            "promptName": p,
                            "contentName": c,
                            "role": role,
                            "text": text,
                        }
                    )
                    if text:
                        print(f"[{role}] {text}")
                        self.transcript.append({"role": role, "text": text.strip()})
                        normalized = text.strip()
                        if role in {"USER", "UNKNOWN"} and normalized and normalized != self._last_user_text:
                            self._last_user_text = normalized
                            await self.user_text_queue.put(normalized)
                        if role in {"ASSISTANT", "UNKNOWN"} and normalized:
                            await self.assistant_text_queue.put(normalized)

                elif "audioOutput" in event:
                    ao = event["audioOutput"]
                    audio_b64 = ao.get("content")
                    if audio_b64:
                        audio_bytes = base64.b64decode(audio_b64)
                        if self.debug_audio:
                            print(f"[AudioOutput] bytes={len(audio_bytes)}")
                        await self.audio_out_queue.put(audio_bytes)

                elif "contentEnd" in event:
                    ce = event["contentEnd"]
                    p = ce.get("promptName", "")
                    c = ce.get("contentName", "")
                    role = self.content_roles.get((p, c), "UNKNOWN")
                    await self._append_event(
                        {
                            "type": "contentEnd",
                            "promptName": p,
                            "contentName": c,
                            "role": role,
                        }
                    )

                elif "error" in event:
                    await self._append_event({"type": "error", "payload": event["error"]})
                    print(f"[Stream error] {event['error']}")
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            print(f"[Response loop error] {exc}")

    async def _play_audio(self) -> None:
        p = pyaudio.PyAudio()
        stream = p.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=OUTPUT_SAMPLE_RATE,
            output=True,
            frames_per_buffer=4096,
            output_device_index=self.output_device_index,
        )
        try:
            while True:
                data = await self.audio_out_queue.get()
                if data is None:
                    break
                await asyncio.get_event_loop().run_in_executor(None, stream.write, data)
        except asyncio.CancelledError:
            pass
        finally:
            stream.stop_stream()
            stream.close()
            p.terminate()

    async def _drain_user_queue(self) -> None:
        while True:
            try:
                self.user_text_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    async def _drain_assistant_queue(self) -> None:
        while True:
            try:
                self.assistant_text_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    async def send_text_instruction(self, text: str) -> None:
        await self._send_user_text(text)

    async def wait_for_assistant_phrase(
        self, phrases: list[str], timeout_s: float = 120.0
    ) -> tuple[bool, str]:
        lower_phrases = [p.lower() for p in phrases]
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout_s
        while loop.time() < deadline:
            wait_left = max(0.0, deadline - loop.time())
            try:
                text = await asyncio.wait_for(
                    self.assistant_text_queue.get(), timeout=min(0.5, wait_left)
                )
            except asyncio.TimeoutError:
                continue
            low = text.lower()
            if any(p in low for p in lower_phrases):
                return True, text
        return False, ""

    async def wait_for_user_utterance(self, timeout_s: float = 12.0, settle_s: float = 0.9) -> str:
        print("[Mic] Listening...")
        self.capture_enabled = True
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout_s
        latest = ""
        last_update = 0.0

        while loop.time() < deadline:
            wait_left = max(0.0, deadline - loop.time())
            try:
                candidate = await asyncio.wait_for(
                    self.user_text_queue.get(), timeout=min(0.4, wait_left)
                )
                latest = candidate.strip()
                last_update = loop.time()
            except asyncio.TimeoutError:
                if latest and last_update and (loop.time() - last_update) >= settle_s:
                    self.capture_enabled = False
                    return latest
                continue

        self.capture_enabled = False
        return latest

    async def speak_text(self, text: str, language: str, timeout_s: float = 10.0) -> PromptResult:
        if not self.session_prompt_name:
            raise RuntimeError("No active prompt. Call start_session first.")
        self.capture_enabled = False
        mark = self._event_mark()
        await self._send_user_text(
            f"Speak to the user in {language}. Say exactly this sentence and nothing else: {text}"
        )

        await self._wait_for(
            lambda e: e.get("type") == "textOutput"
            and e.get("promptName") == self.session_prompt_name
            and e.get("role") in {"ASSISTANT", "UNKNOWN"}
            and bool(e.get("text")),
            mark,
            timeout_s,
        )

        assistant_text = " ".join(
            ev["text"]
            for ev in self.events[mark:]
            if ev.get("type") == "textOutput"
            and ev.get("promptName") == self.session_prompt_name
            and ev.get("role") in {"ASSISTANT", "UNKNOWN"}
            and ev.get("text")
        ).strip()

        if not assistant_text:
            print(f"[Assistant fallback] {text}")

        return PromptResult(prompt_name=self.session_prompt_name, assistant_text=assistant_text, user_text="")

    async def ask_question(self, question_english: str, language: str, timeout_s: float = 30.0) -> PromptResult:
        if not self.session_prompt_name:
            raise RuntimeError("No active prompt. Call start_session first.")
        self.capture_enabled = False
        mark = self._event_mark()
        await self._drain_user_queue()

        await self._send_user_text(
            "Ask exactly one short intake question in "
            f"{language}. Keep meaning exactly as: {question_english}. Do not add extra sentences."
        )
        user_text = await self.wait_for_user_utterance(timeout_s=12.0)
        if not user_text.strip():
            user_text = await self.wait_for_user_utterance(timeout_s=7.0)

        await self._wait_for(
            lambda e: e.get("type") == "textOutput"
            and e.get("promptName") == self.session_prompt_name
            and e.get("role") in {"ASSISTANT", "UNKNOWN"}
            and bool(e.get("text")),
            mark,
            min(timeout_s, 1.5),
        )

        assistant_text = " ".join(
            ev["text"]
            for ev in self.events[mark:]
            if ev.get("type") == "textOutput"
            and ev.get("promptName") == self.session_prompt_name
            and ev.get("role") in {"ASSISTANT", "UNKNOWN"}
            and ev.get("text")
        ).strip()

        return PromptResult(prompt_name=self.session_prompt_name, assistant_text=assistant_text, user_text=user_text)

    async def text_only_assistant(self, instruction: str, timeout_s: float = 10.0) -> str:
        if not self.session_prompt_name:
            raise RuntimeError("No active prompt. Call start_session first.")
        self.capture_enabled = False
        mark = self._event_mark()
        await self._send_user_text(instruction)

        await self._wait_for(
            lambda e: e.get("type") == "textOutput"
            and e.get("promptName") == self.session_prompt_name
            and e.get("role") in {"ASSISTANT", "UNKNOWN"}
            and bool(e.get("text")),
            mark,
            timeout_s,
        )
        return " ".join(
            ev["text"]
            for ev in self.events[mark:]
            if ev.get("type") == "textOutput"
            and ev.get("promptName") == self.session_prompt_name
            and ev.get("role") in {"ASSISTANT", "UNKNOWN"}
            and ev.get("text")
        ).strip()


class HealthIntakeAgent:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.nova = NovaSonicBidiClient(
            model_id=args.model_id,
            region=args.region,
            voice_id=args.voice_id,
            debug_events=args.debug_events,
            debug_audio=args.debug_audio,
            input_device_index=args.input_device_index,
            output_device_index=args.output_device_index,
        )
        self.s3 = boto3.client("s3", region_name=args.region)
        self.translate = boto3.client("translate", region_name=args.region)
        self.record: dict[str, Any] = {
            "language": None,
            "name": None,
            "age": None,
            "location": None,
            "symptoms": {},
            "medical_history": {},
            "exposure_history": {},
            "cough_audio": None,
            "timestamp": None,
        }

    @staticmethod
    def _is_skip(text: str) -> bool:
        t = text.strip().lower()
        return t in {"skip", "please skip", "स्किप", "छोड़ो", "छोड़िए", "छोड़ दें"}

    @staticmethod
    def _detect_language_choice(text: str) -> Optional[str]:
        t = text.strip().lower()
        if any(k in t for k in ["english", "inglish", "अंग्रेज", "एंग्लिश"]):
            return "English"
        if any(k in t for k in ["hindi", "हिंदी", "हिन्दी"]):
            return "Hindi"
        return None

    async def _translate_to_english(self, text: str, source_language: str) -> str:
        if not text:
            return ""
        if source_language.lower() == "english":
            return text.strip()
        source_code = "hi" if source_language.lower() == "hindi" else "auto"
        try:
            resp = self.translate.translate_text(
                Text=text,
                SourceLanguageCode=source_code,
                TargetLanguageCode="en",
            )
            translated = resp.get("TranslatedText", "").strip()
            return translated or text.strip()
        except Exception:
            return text.strip()

    async def _ask_capture(self, question_en: str) -> tuple[str, str]:
        language = self.record["language"] or "English"
        result = await self.nova.ask_question(question_en, language=language)
        raw = result.user_text.strip()
        if not raw:
            return "", ""
        if self._is_skip(raw):
            return raw, ""
        translated = await self._translate_to_english(raw, source_language=language)
        return raw, translated

    async def _ask_until_value(self, key: str, question_en: str, max_tries: int = 2) -> Optional[str]:
        for _ in range(max_tries):
            raw, translated = await self._ask_capture(question_en)
            if not raw:
                continue
            if self._is_skip(raw):
                return None
            if translated:
                self.record[key] = translated
                return translated
        return None

    async def _collect_demographics(self) -> None:
        await self._ask_until_value("name", "Please tell me your full name.")

        age_value = None
        for _ in range(2):
            raw, translated = await self._ask_capture("How old are you?")
            if not raw:
                continue
            if self._is_skip(raw):
                break
            tokens = "".join(ch if ch.isdigit() else " " for ch in translated).split()
            if tokens:
                try:
                    age_value = int(tokens[0])
                    break
                except ValueError:
                    pass
        self.record["age"] = age_value

        await self._ask_until_value("location", "What is your current city or location?")

    async def _collect_symptoms(self) -> None:
        symptoms = self.record["symptoms"]

        raw, fever = await self._ask_capture("Do you have fever? Please answer yes or no.")
        if self._is_skip(raw) or not fever:
            symptoms["fever"] = None
        else:
            yes = fever.lower().startswith("y")
            symptoms["fever"] = yes
            if yes:
                _, temp = await self._ask_capture("What is your temperature, if known?")
                _, duration = await self._ask_capture("How many days have you had fever?")
                symptoms["fever_temperature"] = temp or None
                symptoms["fever_duration"] = duration or None

        raw, cough = await self._ask_capture("Do you have cough? Please say dry, wet, or no cough.")
        symptoms["cough"] = None if self._is_skip(raw) else (cough or None)

        raw, breathing = await self._ask_capture("Do you have difficulty breathing? Please answer yes or no.")
        if self._is_skip(raw) or not breathing:
            symptoms["difficulty_breathing"] = None
        else:
            has_breath_issue = breathing.lower().startswith("y")
            symptoms["difficulty_breathing"] = has_breath_issue
            if has_breath_issue:
                _, severity = await self._ask_capture(
                    "Is the breathing difficulty mild, moderate, or severe?"
                )
                symptoms["breathing_severity"] = severity or None

        raw, fatigue = await self._ask_capture("Do you have fatigue? Please answer yes or no.")
        symptoms["fatigue"] = None if self._is_skip(raw) else (fatigue or None)

        raw, other = await self._ask_capture("Do you have any other symptoms?")
        symptoms["other_symptoms"] = None if self._is_skip(raw) else (other or None)

        no_symptoms = (
            symptoms.get("fever") in [False, None]
            and (symptoms.get("cough") or "").lower() in ["no", "none", "no cough", ""]
            and symptoms.get("difficulty_breathing") in [False, None]
            and (symptoms.get("fatigue") or "").lower() in ["no", "none", ""]
            and not symptoms.get("other_symptoms")
        )
        if no_symptoms:
            _, confirm = await self._ask_capture("To confirm, are you currently without symptoms?")
            symptoms["no_symptoms_confirmed"] = confirm or None

    async def _collect_history(self) -> None:
        mh = self.record["medical_history"]
        _, pre_existing = await self._ask_capture("Do you have any pre-existing medical conditions?")
        mh["pre_existing_conditions"] = pre_existing or None

        _, meds = await self._ask_capture("Are you currently taking any medications?")
        mh["current_medications"] = meds or None

    async def _collect_exposure(self) -> None:
        ex = self.record["exposure_history"]
        _, sick_contact = await self._ask_capture(
            "Have you had recent contact with someone who was sick?"
        )
        ex["recent_sick_contact"] = sick_contact or None

        _, travel = await self._ask_capture("Have you traveled recently?")
        ex["recent_travel"] = travel or None

    @staticmethod
    def _validate_cough_from_rms(rms_values: list[int]) -> tuple[bool, int]:
        if not rms_values:
            return False, 0
        peak = max(rms_values)
        baseline = sorted(rms_values)[len(rms_values) // 2]
        threshold = max(800, int(baseline * 2.2), int(peak * 0.45))

        cough_count = 0
        cooldown = 0
        for v in rms_values:
            if cooldown > 0:
                cooldown -= 1
                continue
            if v >= threshold:
                cough_count += 1
                cooldown = 8

        return cough_count >= 3, cough_count

    def _open_input_stream_with_fallback(self, p: pyaudio.PyAudio):
        try:
            return p.open(
                format=FORMAT,
                channels=CHANNELS,
                rate=INPUT_SAMPLE_RATE,
                input=True,
                frames_per_buffer=CHUNK_SIZE,
                input_device_index=self.args.input_device_index,
            )
        except Exception:
            return p.open(
                format=FORMAT,
                channels=CHANNELS,
                rate=INPUT_SAMPLE_RATE,
                input=True,
                frames_per_buffer=CHUNK_SIZE,
            )

    def _record_cough_wav(self, out_path: str, seconds: int = 8) -> tuple[bool, int]:
        attempts = 2
        last_exc: Optional[Exception] = None

        for attempt in range(1, attempts + 1):
            p = pyaudio.PyAudio()
            stream = None
            try:
                stream = self._open_input_stream_with_fallback(p)
                frames: list[bytes] = []
                rms_values: list[int] = []

                print("[Cough] Beep... now cough three times.")
                print("\a", end="", flush=True)

                for _ in range(int(INPUT_SAMPLE_RATE / CHUNK_SIZE * seconds)):
                    data = stream.read(CHUNK_SIZE, exception_on_overflow=False)
                    frames.append(data)
                    rms_values.append(pcm16_rms(data))

                with wave.open(out_path, "wb") as wf:
                    wf.setnchannels(CHANNELS)
                    wf.setsampwidth(2)
                    wf.setframerate(INPUT_SAMPLE_RATE)
                    wf.writeframes(b"".join(frames))

                return self._validate_cough_from_rms(rms_values)
            except Exception as exc:
                last_exc = exc
                print(f"[Cough recording warning] attempt {attempt} failed: {exc}")
                time.sleep(0.5)
            finally:
                if stream is not None:
                    stream.stop_stream()
                    stream.close()
                p.terminate()

        if last_exc:
            raise RuntimeError(f"Failed to record cough audio: {last_exc}")
        raise RuntimeError("Failed to record cough audio")

    def _upload_file_to_s3(self, local_path: str, key: str) -> str:
        bucket = self.args.s3_bucket
        if not bucket:
            raise ValueError("--s3-bucket is required for S3 uploads")

        self.s3.upload_file(local_path, bucket, key)
        return f"s3://{bucket}/{key}"

    def _upload_json_to_s3(self, payload: dict[str, Any], key: str) -> str:
        bucket = self.args.s3_bucket
        if not bucket:
            raise ValueError("--s3-bucket is required for S3 uploads")

        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=body,
            ContentType="application/json",
        )
        return f"s3://{bucket}/{key}"

    async def _extract_structured_from_transcript(self) -> dict[str, Any]:
        lines = []
        for turn in self.nova.transcript[-200:]:
            role = turn.get("role", "UNKNOWN")
            text = turn.get("text", "")
            if text:
                lines.append(f"{role}: {text}")
        transcript_text = "\\n".join(lines)

        instruction = (
            "Extract a structured English health intake JSON from the transcript. "
            "Return JSON only, no markdown. Use this schema keys exactly: "
            "language, name, age, location, symptoms, medical_history, exposure_history. "
            "Use null for unknown. For symptoms, include fever, fever_temperature, fever_duration, "
            "cough, difficulty_breathing, breathing_severity, fatigue, other_symptoms. "
            "For medical_history include pre_existing_conditions and current_medications. "
            "For exposure_history include recent_sick_contact and recent_travel. "
            f"Transcript:\\n{transcript_text}"
        )
        raw = await self.nova.text_only_assistant(instruction, timeout_s=20.0)
        if not raw:
            return {}
        try:
            start = raw.find("{")
            end = raw.rfind("}")
            if start >= 0 and end > start:
                return json.loads(raw[start : end + 1])
        except Exception:
            return {}
        return {}

    async def run(self) -> None:
        await self.nova.start_session(HEALTH_SYSTEM_PROMPT)

        await self.nova.send_text_instruction(
            "Start the live health intake call now. "
            "First ask exactly: Please choose your language: English or Hindi? "
            "Then continue the complete intake conversation in the selected language. "
            "If Hindi is selected, use clear native Hindi wording (Devanagari) and avoid English words. "
            "If English is selected, use only English. "
            "Ask one question at a time and adapt based on responses. "
            "Allow skip. Collect: name, age, location, symptoms, medical history, exposure history. "
            "When done, say exactly: Now I will record your cough. Please cough three times after the beep."
        )

        detected, _ = await self.nova.wait_for_assistant_phrase(
            ["now i will record your cough", "please cough three times after the beep"],
            timeout_s=300.0,
        )
        if not detected:
            raise RuntimeError("Conversation timeout: cough phase trigger was not reached.")

        await self.nova.end_session()

        # Derive structured fields from transcript (English JSON).
        await self.nova.start_session(HEALTH_SYSTEM_PROMPT)
        extracted = await self._extract_structured_from_transcript()
        await self.nova.end_session()
        if isinstance(extracted, dict):
            self.record.update(
                {
                    "language": extracted.get("language") or self.record.get("language"),
                    "name": extracted.get("name") or self.record.get("name"),
                    "age": extracted.get("age") if extracted.get("age") is not None else self.record.get("age"),
                    "location": extracted.get("location") or self.record.get("location"),
                    "symptoms": extracted.get("symptoms") or self.record.get("symptoms", {}),
                    "medical_history": extracted.get("medical_history")
                    or self.record.get("medical_history", {}),
                    "exposure_history": extracted.get("exposure_history")
                    or self.record.get("exposure_history", {}),
                }
            )

        cough_local_path = self.args.cough_wav
        valid_cough, cough_count = self._record_cough_wav(cough_local_path)
        print(f"[Cough validation] valid={valid_cough}, detected_bursts={cough_count}")

        cough_key = f"health-intake/cough/{uuid.uuid4()}.wav"
        cough_s3 = self._upload_file_to_s3(cough_local_path, cough_key)
        self.record["cough_audio"] = cough_s3

        self.record["timestamp"] = datetime.now(timezone.utc).isoformat()

        json_key = f"health-intake/json/{uuid.uuid4()}.json"
        json_s3 = self._upload_json_to_s3(self.record, json_key)

        await self.nova.start_session(HEALTH_SYSTEM_PROMPT)
        await self.nova.speak_text("Thank you, your assessment is complete.", language="English")
        await asyncio.sleep(0.8)
        await self.nova.end_session()

        print("\nFinal intake JSON:")
        print(json.dumps(self.record, ensure_ascii=False, indent=2))
        print(f"\nJSON uploaded to: {json_s3}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AWS Nova 2 Sonic Health Intake Agent")
    parser.add_argument("--region", default=os.getenv("AWS_REGION", "us-east-1"))
    parser.add_argument("--model-id", default="amazon.nova-2-sonic-v1:0")
    parser.add_argument("--voice-id", default="matthew")
    parser.add_argument("--s3-bucket", required=True)
    parser.add_argument("--cough-wav", default="cough_recording.wav")
    parser.add_argument("--debug-events", action="store_true")
    parser.add_argument("--debug-audio", action="store_true")
    parser.add_argument("--input-device-index", type=int, default=None)
    parser.add_argument("--output-device-index", type=int, default=None)
    parser.add_argument("--list-audio-devices", action="store_true")
    return parser.parse_args()


def print_audio_devices() -> None:
    p = pyaudio.PyAudio()
    try:
        count = p.get_device_count()
        print(f"Detected {count} audio devices:")
        for i in range(count):
            info = p.get_device_info_by_index(i)
            name = info.get("name", "unknown")
            in_ch = int(info.get("maxInputChannels", 0))
            out_ch = int(info.get("maxOutputChannels", 0))
            default_sr = int(info.get("defaultSampleRate", 0))
            print(f"[{i}] {name} | input_ch={in_ch} output_ch={out_ch} default_sr={default_sr}")
    finally:
        p.terminate()


async def main() -> None:
    args = parse_args()
    if args.list_audio_devices:
        print_audio_devices()
        return
    agent = HealthIntakeAgent(args)
    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())
