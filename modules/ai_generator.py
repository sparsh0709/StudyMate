"""AI generator — sends rendered prompts to the OpenAI API.

The study pack is produced by three independent prompt tasks (SUMMARY,
QUESTIONS, REVISION). They run in parallel threads, so a pack takes roughly
as long as the slowest single task rather than the sum of all three.

Design notes for the viva:
* The API key is never hard-coded. It is read from the environment (.env via
  python-dotenv) or passed in from Streamlit secrets / the sidebar.
* Newer OpenAI reasoning models reject some parameters (e.g. ``temperature``)
  while older models reject others (``reasoning_effort``). Instead of
  hard-coding a model list, the client drops a rejected optional parameter and
  retries once. Every dropped parameter is recorded in the result, so
  experiments stay transparent.
* Transient failures (rate limit, connection, timeout, 5xx) are retried with
  exponential backoff; all other errors are turned into readable messages.
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

DEFAULT_MODEL = "gpt-5.4-mini"
OPTIONAL_PARAMS = ("temperature", "reasoning_effort")
MAX_RETRIES = 2


@dataclass
class GenerationSettings:
    model: str = DEFAULT_MODEL
    temperature: float | None = None
    reasoning_effort: str | None = "low"
    max_output_tokens: int = 4000

    @classmethod
    def from_env(cls) -> "GenerationSettings":
        temp = os.getenv("OPENAI_TEMPERATURE", "").strip()
        effort = os.getenv("OPENAI_REASONING_EFFORT", "low").strip()
        return cls(
            model=os.getenv("OPENAI_MODEL", "").strip() or DEFAULT_MODEL,
            temperature=float(temp) if temp else None,
            reasoning_effort=effort or None,
            max_output_tokens=int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "4000") or 4000),
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
        return [f"{k}: {t.error}" for k, t in self.tasks.items() if t.error]


def get_api_key(explicit: str | None = None) -> str | None:
    """Explicit key (sidebar/secrets) wins over the OPENAI_API_KEY env variable."""
    key = (explicit or os.getenv("OPENAI_API_KEY") or "").strip()
    if not key or key.startswith("sk-your-key"):
        return None
    return key


def make_client(api_key: str | None = None):
    """Create an OpenAI client. Import is lazy so the rest of the app works without it."""
    from openai import OpenAI

    key = get_api_key(api_key)
    if not key:
        raise RuntimeError(
            "No OpenAI API key found. Add OPENAI_API_KEY to your .env file "
            "(see .env.example) or enter a key in the sidebar."
        )
    return OpenAI(api_key=key, timeout=90.0)


def _friendly_error(exc: Exception) -> str:
    name = type(exc).__name__
    msg = str(exc)
    if name == "AuthenticationError":
        return "The OpenAI API key was rejected. Check OPENAI_API_KEY in your .env file."
    if name == "PermissionDeniedError":
        return "This API key does not have access to the selected model."
    if name == "NotFoundError":
        return "The selected model was not found. Check OPENAI_MODEL in your .env file."
    if name == "RateLimitError":
        if "quota" in msg.lower():
            return "Your OpenAI account has no remaining quota/credit."
        return "Rate limit reached. Wait a few seconds and try again."
    if name in ("APIConnectionError", "APITimeoutError"):
        return "Could not reach the OpenAI API. Check your internet connection."
    return f"{name}: {msg[:300]}"


def _is_transient(exc: Exception) -> bool:
    name = type(exc).__name__
    if name in ("APIConnectionError", "APITimeoutError", "InternalServerError"):
        return True
    return name == "RateLimitError" and "quota" not in str(exc).lower()


def _rejected_param(exc: Exception, params: dict[str, Any]) -> str | None:
    """If a BadRequest complains about one of our optional params, return its name."""
    if type(exc).__name__ != "BadRequestError":
        return None
    msg = str(exc).lower()
    for p in OPTIONAL_PARAMS:
        if p in params and p in msg:
            return p
    return None


def call_model(client, messages: list[dict[str, str]], settings: GenerationSettings,
               task: str = "", sleep: Callable[[float], None] = time.sleep) -> TaskResult:
    """Run one chat completion and return a TaskResult (never raises)."""
    params: dict[str, Any] = {
        "model": settings.model,
        "messages": messages,
        "max_completion_tokens": settings.max_output_tokens,
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
                result.output_tokens = getattr(usage, "completion_tokens", None)
            if not result.text:
                result.error = (
                    "The model returned an empty response"
                    + (" (output token limit reached — increase OPENAI_MAX_OUTPUT_TOKENS)."
                       if choice.finish_reason == "length" else ".")
                )
            break
        except Exception as exc:  # noqa: BLE001 — we convert every failure to a message
            bad = _rejected_param(exc, params)
            if bad:
                params.pop(bad)
                result.dropped_params.append(bad)
                continue
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
    """Run the three prompt tasks for one prompt version, in parallel."""
    settings = settings or GenerationSettings.from_env()
    client = client or make_client(api_key)

    def run(task: str) -> TaskResult:
        msgs = render_messages(version, task, notes, subject, detail_level)
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
