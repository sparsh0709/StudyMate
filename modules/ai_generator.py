i have 
"""AI generator — sends rendered prompts to the Gemini API
through Google's OpenAI-compatible endpoint.
"""

from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable

from dotenv import load_dotenv

from modules.prompt_manager import DEFAULT_DETAIL, TASKS, render_messages

load_dotenv()

DEFAULT_MODEL = "gemini-3.6-flash"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
MAX_RETRIES = 2


@dataclass
class GenerationSettings:
    model: str = DEFAULT_MODEL
    temperature: float | None = None
    reasoning_effort: str | None = "low"
    max_output_tokens: int = 4000

    @classmethod
    def from_env(cls) -> "GenerationSettings":
        temp = os.getenv("GEMINI_TEMPERATURE", "").strip()
        effort = os.getenv("GEMINI_REASONING_EFFORT", "low").strip()

        return cls(
            model=os.getenv("GEMINI_MODEL", "").strip() or DEFAULT_MODEL,
            temperature=float(temp) if temp else None,
            reasoning_effort=effort or None,
            max_output_tokens=int(
                os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "4000") or 4000
            ),
        )


@dataclass
class TaskResult:
    task: str
    text: str = ""
    error: str | None = None
    latency_s: float = 0.0
    input_tokens: int | None = None
    output_tokens: int | None = None
    finish_reason: str | None = None
    dropped_params: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.text.strip())


@dataclass
class StudyPackResult:
    version: str
    model: str
    subject: str
    detail_level: str
    tasks: dict[str, TaskResult]
    total_latency_s: float

    @property
    def ok(self) -> bool:
        return all(t.ok for t in self.tasks.values())

    @property
    def errors(self) -> list[str]:
        return [
            f"{k}: {t.error}"
            for k, t in self.tasks.items()
            if t.error
        ]


def get_api_key(explicit: str | None = None) -> str | None:
    """Get Gemini key from explicit input or environment."""
    key = (explicit or os.getenv("GEMINI_API_KEY") or "").strip()

    if not key or key == "your-gemini-key":
        return None

    return key


def make_client(api_key: str | None = None):
    """Create a Gemini client using OpenAI compatibility."""
    from openai import OpenAI

    key = get_api_key(api_key)

    if not key:
        raise RuntimeError(
            "No Gemini API key found. Add GEMINI_API_KEY to your .env "
            "file or Streamlit Secrets."
        )

    return OpenAI(
        api_key=key,
        base_url=GEMINI_BASE_URL,
        timeout=90.0,
        max_retries=0,
    )


def _friendly_error(exc: Exception) -> str:
    name = type(exc).__name__
    msg = str(exc)

    if name == "AuthenticationError":
        return "Gemini API key rejected. Check your GEMINI_API_KEY."

    if name == "PermissionDeniedError":
        return "Your Gemini API key does not have permission to use this API."

    if name == "NotFoundError":
        return "Gemini model not found. Check your GEMINI_MODEL setting."

    if name == "RateLimitError":
        lower = msg.lower()

        if any(word in lower for word in ("quota", "billing", "limit: 0")):
            return (
                "Gemini API quota exhausted. Check your Google AI Studio "
                "usage and rate limits."
            )

        return "Gemini rate limit reached. Wait briefly and try again."

    if name in ("APIConnectionError", "APITimeoutError"):
        return "Could not connect to Gemini. Check your internet connection."

    return f"{name}: {msg[:300]}"


def _is_transient(exc: Exception) -> bool:
    name = type(exc).__name__

    if name in (
        "APIConnectionError",
        "APITimeoutError",
        "InternalServerError",
    ):
        return True

    return name == "RateLimitError" and not any(
        word in str(exc).lower()
        for word in ("quota", "billing", "limit: 0")
    )


def call_model(
    client,
    messages: list[dict[str, str]],
    settings: GenerationSettings,
    task: str = "",
    sleep: Callable[[float], None] = time.sleep,
) -> TaskResult:
    """Run one Gemini chat completion and return a TaskResult."""
    params: dict[str, Any] = {
        "model": settings.model,
        "messages": messages,
        "max_tokens": settings.max_output_tokens,
    }

    if settings.temperature is not None:
        params["temperature"] = settings.temperature

    if settings.reasoning_effort:
        params["reasoning_effort"] = settings.reasoning_effort

    result = TaskResult(task=task)
    attempt = 0
    start = time.perf_counter()

    while True:
        try:
            resp = client.chat.completions.create(**params)
            choice = resp.choices[0]

            result.text = (choice.message.content or "").strip()
            result.finish_reason = choice.finish_reason

            usage = getattr(resp, "usage", None)

            if usage is not None:
                result.input_tokens = getattr(usage, "prompt_tokens", None)
                result.output_tokens = getattr(
                    usage, "completion_tokens", None
                )

            if not result.text:
                result.error = (
                    "Gemini returned an empty response"
                    + (
                        " (output token limit reached)."
                        if choice.finish_reason == "length"
                        else "."
                    )
                )

            break

        except Exception as exc:
            if _is_transient(exc) and attempt < MAX_RETRIES:
                attempt += 1
                sleep(2 ** attempt)
                continue

            result.error = _friendly_error(exc)
            break

    result.latency_s = round(time.perf_counter() - start, 2)
    return result


def generate_study_pack(
    notes: str,
    subject: str = "",
    version: str = "v3",
    detail_level: str = DEFAULT_DETAIL,
    client=None,
    settings: GenerationSettings | None = None,
    api_key: str | None = None,
) -> StudyPackResult:
    """Run the three study-pack tasks in parallel."""
    settings = settings or GenerationSettings.from_env()
    client = client or make_client(api_key)

    def run(task: str) -> TaskResult:
        msgs = render_messages(
            version, task, notes, subject, detail_level
        )
        return call_model(client, msgs, settings, task=task)

    start = time.perf_counter()

    with ThreadPoolExecutor(max_workers=len(TASKS)) as pool:
        results = dict(zip(TASKS, pool.map(run, TASKS)))

    return StudyPackResult(
        version=version,
        model=settings.model,
        subject=subject,
        detail_level=detail_level,
        tasks=results,
        total_latency_s=round(time.perf_counter() - start, 2),
    )
