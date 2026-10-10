"""Bounded generation calls: no nested SDK retries or unbounded reasoning.

Each request owns its async HTTP client; cancellation closes the connection.
Used by generation only, not by the interactive editors or document vision.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import math
import re
import threading
import time
from uuid import uuid4

import httpx
from langchain_core.messages import AIMessage

from app import llm_models

logger = logging.getLogger(__name__)
_metrics_lock = threading.Lock()
_unavailable_until = {}
# Endpoints can change their requirements between catalog updates. Remember a
# confirmed rejection so later calls do not repeat a known-invalid setting.
_reasoning_required = set()


class GenerationTimeout(TimeoutError):
    def __init__(self, message, *, kind="total"):
        super().__init__(message)
        self.kind = kind


class GenerationStreamError(RuntimeError):
    status_code = 502


@dataclass(frozen=True)
class RequestBudget:
    total: float
    first_response: float
    idle: float


# Initial budgets, not calibrated latency guarantees. Input size influences
# waiting time; extra output capacity also gets a bounded allowance.
_BUDGETS = {
    "evidence": (90, 150, 6144),
    "evidence_batch": (120, 180, 6144),
    "glossary": (150, 180, 4096),
    "flashcards": (90, 150, 4096),
    "content": (150, 240, 10000),
    "content_repair": (120, 180, 10000),
    "diagrams": (60, 90, 4096),
}


def request_budget(purpose, input_chars, max_tokens, deadline=None):
    base, ceiling, usual_output = _BUDGETS.get(purpose, (90, 120, 4096))
    input_steps = math.ceil(max(0, input_chars - 8000) / 8000)
    output_steps = math.ceil(max(0, max_tokens - usual_output) / 2048)
    total = float(deadline) if deadline is not None else min(ceiling, base + 15 * (input_steps + output_steps))
    if not math.isfinite(total) or total <= 0:
        raise ValueError("El límite de generación debe ser positivo y finito.")
    first = min(total, max(90, min(180, total * 0.8)))
    idle = min(total, 60 if purpose in {"content", "content_repair", "glossary"} else 45)
    return RequestBudget(total, first, idle)


def snapshot_metrics(metrics):
    with _metrics_lock:
        return deepcopy(metrics)


def update_metrics(metrics, **values):
    with _metrics_lock:
        metrics.update(values)


def _text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(item.get("text", "") for item in content if isinstance(item, dict) and item.get("type") in {"text", "text_delta"})
    return ""


def _input_chars(messages):
    if isinstance(messages, str):
        return len(messages)
    return sum(len(_text(item.get("content", "") if isinstance(item, dict) else getattr(item, "content", "")))
        if not isinstance(item, str) else len(item) for item in messages)


async def with_deadline(request, seconds):
    try:
        return await asyncio.wait_for(request(), timeout=seconds)
    except GenerationTimeout:
        raise
    except asyncio.TimeoutError as exc:
        raise GenerationTimeout(f"El proveedor excedió el límite de {seconds:g} s de la llamada.") from exc


class GenerationClient:
    def __init__(self, resolved, purpose, *, max_tokens=4096, deadline=None, schema=None, metrics=None, progress=None):
        self.resolved, self.purpose = resolved, purpose
        self.max_tokens, self.deadline, self.schema = max_tokens, deadline, schema
        self.metrics = metrics if metrics is not None else {}
        self.progress = progress

    def invoke(self, messages):
        with _metrics_lock:
            unavailable = _unavailable_until.get(self.resolved.model_id, 0) > time.monotonic()
        if unavailable and self.resolved.role == "query_expansion":
            self._use_alternate()
        try:
            return self._invoke_compatible(messages)
        except Exception as error:
            temporary = isinstance(error, (GenerationTimeout, httpx.TimeoutException)) or getattr(error, "status_code", None) in {429, 502, 503, 504} or re.search(r"\b(?:429|502|503|504|timed? out)\b", str(error), re.I)
            if self.resolved.role != "query_expansion" or not temporary:
                raise
            with _metrics_lock:
                _unavailable_until[self.resolved.model_id] = time.monotonic() + 300
            if not self._use_alternate():
                raise
            return self._invoke_compatible(messages)

    def _reasoning_options(self):
        definition = llm_models.get_model_definition(self.resolved.role, self.resolved.model_id) or {}
        policy = definition.get("reasoning", {})
        with _metrics_lock:
            mandatory = policy.get("mandatory", False) or self.resolved.model_id in _reasoning_required
        if self.resolved.role == "query_expansion" and not mandatory:
            return {"enabled": False}
        efforts = policy.get("supported_efforts", [])
        effort = "minimal" if self.resolved.role == "query_expansion" and "minimal" in efforts else "low"
        return {"effort": effort, "exclude": True}

    def _invoke_compatible(self, messages):
        reasoning_disabled = self._reasoning_options().get("enabled") is False
        try:
            return self._invoke_once(messages)
        except Exception as error:
            # Only this explicit, request-configuration error is recoverable.
            # Do not retry arbitrary 400s or loop through provider failures.
            mandatory_rejection = (
                self.resolved.transport == llm_models.OPENROUTER_TRANSPORT
                and getattr(error, "status_code", None) == 400
                and reasoning_disabled
                and re.search(r"reasoning is mandatory.*cannot be disabled", str(error), re.I | re.S)
            )
            if not mandatory_rejection:
                raise
            with _metrics_lock:
                _reasoning_required.add(self.resolved.model_id)
                self.metrics["reasoning_adjustments"] = self.metrics.get("reasoning_adjustments", 0) + 1
            logger.warning("Generation reasoning compatibility phase=%s model=%s: retrying once with low effort",
                self.purpose, self.resolved.model_id)
            return self._invoke_once(messages)

    def _use_alternate(self):
        candidate = next((item for item in llm_models.MODEL_CATALOG[self.resolved.role]
            if item["id"] != self.resolved.model_id and llm_models.model_is_configured(item)
            and _unavailable_until.get(item["id"], 0) <= time.monotonic()), None)
        if not candidate:
            return False
        previous = self.resolved.model_id
        self.resolved = llm_models.resolve_model(self.resolved.role, candidate["id"], allow_fallback=False)
        with _metrics_lock:
            self.metrics["auxiliary_fallback"] = True
            self.metrics["auxiliary_model_effective"] = self.resolved.model_id
        logger.warning("Generation temporary fallback phase=%s requested=%s effective=%s", self.purpose, previous, self.resolved.model_id)
        return True

    def _invoke_once(self, messages):
        budget = request_budget(self.purpose, _input_chars(messages), self.max_tokens, self.deadline)
        started = time.monotonic()
        record = {"id": str(uuid4()), "phase": self.purpose, "model": self.resolved.model_id,
            "model_name": self.resolved.name, "status": "waiting", "started_at": datetime.now(timezone.utc).isoformat(),
            "deadline_s": budget.total, "first_response_limit_s": budget.first_response, "idle_limit_s": budget.idle,
            "input_chars": _input_chars(messages), "output_chars": 0, "chunks": 0, "elapsed_ms": 0}
        with _metrics_lock:
            self.metrics["llm_requests"] = [*self.metrics.get("llm_requests", [])[-63:], record]

        def update(**values):
            with _metrics_lock:
                record.update(values)
                record["elapsed_ms"] = round((time.monotonic() - started) * 1000)

        def publish():
            update()
            if self.progress:
                try:
                    self.progress(snapshot_metrics(self.metrics))
                except Exception:
                    # Observability must not discard an otherwise valid response.
                    logger.warning("Unable to publish generation progress phase=%s", self.purpose, exc_info=True)

        async def heartbeat():
            while True:
                await asyncio.sleep(5)
                publish()
                logger.info("Generation progress phase=%s model=%s elapsed_ms=%s first_token_ms=%s output_chars=%s",
                    self.purpose, self.resolved.model_id, record["elapsed_ms"], record.get("first_token_ms"), record["output_chars"])

        async def request():
            # Reading may legitimately wait for the first token; the independent
            # first-response/idle timers below do not mistake SSE keepalives for output.
            timeout = httpx.Timeout(budget.first_response, connect=15, write=30, pool=15)
            async with httpx.AsyncClient(timeout=timeout) as http_client:
                options = {"http_async_client": http_client} if self.resolved.transport == llm_models.OPENROUTER_TRANSPORT else {}
                definition = llm_models.get_model_definition(self.resolved.role, self.resolved.model_id) or {}
                response_format = ({"type": "json_schema", "json_schema": {
                    "name": self.purpose, "strict": True, "schema": self.schema}}
                    if self.schema and "structured_output" in definition.get("capabilities", []) else None)
                if self.resolved.transport == llm_models.OPENROUTER_TRANSPORT:
                    options["extra_body"] = {"reasoning": self._reasoning_options()}
                    if response_format:
                        # Keep the schema in the wire payload while avoiding
                        # LangChain's beta parsing stream, which loses OpenRouter
                        # usage frames. JSON is validated after full assembly.
                        options["extra_body"]["response_format"] = response_format
                model = llm_models.create_chat_model(self.resolved, timeout=timeout, max_retries=0,
                    max_tokens=self.max_tokens, **options)
                if response_format and self.resolved.transport != llm_models.OPENROUTER_TRANSPORT:
                    model = model.bind(response_format=response_format)
                kwargs = {"stream_usage": True} if self.resolved.transport == llm_models.OPENROUTER_TRANSPORT else {}
                stream = model.astream(messages, **kwargs)
                pieces, metadata, usage = [], {}, None
                last_output = None
                try:
                    while True:
                        now = time.monotonic()
                        remaining = (started + budget.first_response - now) if last_output is None else (last_output + budget.idle - now)
                        kind = "first_response" if last_output is None else "idle"
                        try:
                            chunk = await asyncio.wait_for(anext(stream), timeout=max(0, remaining))
                        except StopAsyncIteration:
                            break
                        except asyncio.TimeoutError as exc:
                            message = (f"El proveedor no envió contenido en {budget.first_response:g} s."
                                if kind == "first_response" else f"La respuesta dejó de avanzar durante {budget.idle:g} s.")
                            raise GenerationTimeout(message, kind=kind) from exc
                        received = time.monotonic()
                        if "first_event_ms" not in record:
                            update(first_event_ms=round((received - started) * 1000))
                        text = _text(chunk.content)
                        if text:
                            pieces.append(text)
                            last_output = received
                            first_output = "first_token_ms" not in record
                            update(status="generating", output_chars=record["output_chars"] + len(text), chunks=record["chunks"] + 1,
                                last_output_at=datetime.now(timezone.utc).isoformat(), last_output_ms=round((received - started) * 1000),
                                **({"first_token_ms": round((received - started) * 1000)} if first_output else {}))
                            if first_output:
                                publish()
                        chunk_metadata = getattr(chunk, "response_metadata", {}) or {}
                        if chunk_metadata.get("finish_reason") == "error" or chunk_metadata.get("error"):
                            raise GenerationStreamError("El proveedor interrumpió la respuesta; no se guardará contenido parcial.")
                        metadata.update(chunk_metadata)
                        if getattr(chunk, "usage_metadata", None):
                            # Schema streams can repeat final usage. These are
                            # totals, not increments; never double their tokens.
                            usage = chunk.usage_metadata
                    if metadata.get("finish_reason") not in {"stop", "length", "max_tokens"}:
                        raise GenerationStreamError("La respuesta terminó sin confirmar su finalización; no se guardará contenido parcial.")
                    if not pieces:
                        raise ValueError("El proveedor devolvió una respuesta vacía.")
                    return AIMessage(content="".join(pieces), response_metadata=metadata, usage_metadata=usage)
                finally:
                    await stream.aclose()

        async def monitored_request():
            task = asyncio.create_task(heartbeat())
            try:
                return await with_deadline(request, budget.total)
            finally:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        response = None
        publish()
        try:
            response = asyncio.run(monitored_request())
            metadata = getattr(response, "response_metadata", {}) or {}
            if metadata.get("finish_reason") in {"length", "max_tokens"}:
                raise ValueError("La respuesta alcanzó su límite de salida; no se guardará contenido incompleto.")
            update(status="complete")
            return response
        except Exception as error:
            update(status="timeout" if isinstance(error, (GenerationTimeout, httpx.TimeoutException)) else "error",
                **({"timeout_kind": error.kind} if isinstance(error, GenerationTimeout) else {}))
            raise
        finally:
            elapsed = round((time.monotonic() - started) * 1000)
            usage = getattr(response, "usage_metadata", None) or {}
            with _metrics_lock:
                self.metrics["llm_calls"] = self.metrics.get("llm_calls", 0) + 1
                self.metrics["llm_ms"] = self.metrics.get("llm_ms", 0) + elapsed
                calls = dict(self.metrics.get("calls_by_phase", {}))
                calls[self.purpose] = calls.get(self.purpose, 0) + 1
                self.metrics["calls_by_phase"] = calls
                for token in ("input_tokens", "output_tokens"):
                    value = usage.get(token)
                    if isinstance(value, int):
                        self.metrics[token] = self.metrics.get(token, 0) + value
                details = usage.get("output_token_details", {}) or {}
                if isinstance(details.get("reasoning"), int):
                    self.metrics["reasoning_tokens"] = self.metrics.get("reasoning_tokens", 0) + details["reasoning"]
            publish()
            logger.info("Generation phase=%s model=%s elapsed_ms=%s status=%s deadline_s=%s first_token_ms=%s output_chars=%s usage=%s",
                self.purpose, self.resolved.model_id, elapsed, record["status"], budget.total, record.get("first_token_ms"), record["output_chars"], usage)


def array_schema(name, properties):
    return {"type": "object", "properties": {name: {"type": "array", "items": {
        "type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}}},
        "required": [name], "additionalProperties": False}
