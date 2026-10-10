import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import time
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
from openai import BadRequestError
from langchain_core.messages import AIMessageChunk

from app import llm_models
from app.evidence_inputs import relevant_history, terms
from app.generation_runtime import GenerationClient, GenerationStreamError, GenerationTimeout, RequestBudget, request_budget, with_deadline
from app.knowledge import embed_with_cache
from app.worker import _store_embedding
from app.reference_checks import reference_checks
from app.v2_agent import _flashcard_call, _card_key, normalize_body_headings, validate_body_markdown


def streaming_model(*responses):
    sequence = iter(responses)
    def stream(*_args, **_kwargs):
        response = next(sequence)
        async def chunks():
            if isinstance(response, Exception):
                raise response
            usage = getattr(response, "usage_metadata", None)
            if usage:
                usage = {**usage, "total_tokens": usage.get("total_tokens", usage.get("input_tokens", 0) + usage.get("output_tokens", 0))}
            yield AIMessageChunk(content=response.content, response_metadata=getattr(response, "response_metadata", {"finish_reason": "stop"}), usage_metadata=usage)
        return chunks()
    model = SimpleNamespace(astream=MagicMock(side_effect=stream))
    model.bind = MagicMock(return_value=model)
    return model


class DeadlineTests(unittest.IsolatedAsyncioTestCase):
    async def test_wall_deadline_cancels_even_a_request_that_keeps_receiving_data(self):
        cancelled = []
        async def request():
            try:
                while True:
                    await asyncio.sleep(0.001)
            finally:
                cancelled.append(True)
        started = time.monotonic()
        with self.assertRaises(GenerationTimeout):
            await with_deadline(request, 0.02)
        self.assertLess(time.monotonic() - started, 0.2)
        self.assertEqual(cancelled, [True])


class GenerationQualityTests(unittest.TestCase):
    def state(self, **changes):
        state = dict(metrics={}, flashcard_count=19, body_markdown="El kernel administra recursos. ls -a muestra archivos ocultos.",
            historical_context={}, evidence_manifest=[{"concept": "ls -a", "statement": "Lista archivos ocultos", "novelty_relation": "APPLIES"}])
        state.update(changes)
        return state

    def note(self):
        return SimpleNamespace(course_name="Curso", course_module="Módulo")

    def test_smaller_useful_card_set_does_not_fail_a_whole_note(self):
        llm = MagicMock()
        llm.invoke.return_value = SimpleNamespace(content=json.dumps({"flashcards": [{"question": "¿Qué muestra ls -a?", "answer": "Incluye archivos ocultos."}]}))
        state = self.state()
        result = _flashcard_call(llm, self.note(), state)
        self.assertIn("¿Qué muestra ls -a?::Incluye archivos ocultos.", result)
        self.assertEqual(state["metrics"]["flashcards_generated"], 1)
        self.assertEqual(llm.invoke.call_count, 1)

    def test_repetition_only_skips_cards_without_inventing_new_questions(self):
        llm = MagicMock()
        state = self.state(evidence_manifest=[{"statement": "Teoría anterior", "novelty_relation": "REPEATS"}])
        _flashcard_call(llm, self.note(), state)
        llm.invoke.assert_not_called()
        self.assertEqual(state["metrics"]["flashcards_generated"], 0)

    def test_deduplication_checks_all_history_not_only_prompt_subset(self):
        old = {"question": "¿Qué muestra ls -a?", "answer": "Incluye archivos ocultos."}
        new = {"question": "¿Cómo se filtra con grep?", "answer": "grep patrón archivo filtra líneas."}
        llm = MagicMock()
        llm.invoke.return_value = SimpleNamespace(content=json.dumps({"flashcards": [old, old, new]}))
        state = self.state(historical_context={"flashcards": [], "flashcard_history": [old]})
        result = _flashcard_call(llm, self.note(), state)
        self.assertNotIn(old["question"] + "::", result)
        self.assertIn(new["question"], result)
        self.assertEqual(state["metrics"]["flashcards_duplicates_rejected"], 2)

    def test_short_commands_remain_distinguishable(self):
        self.assertNotEqual(terms("¿Qué hace cp?"), terms("¿Qué hace cd?"))
        rows = [{"text": "cd cambia de directorio"}, {"text": "cp copia archivos"}]
        result = relevant_history(rows, "cp copia archivos", text=lambda item: item["text"])
        self.assertEqual(result, [rows[1]])
        self.assertNotEqual(_card_key("grep -i"), _card_key("grep -I"))
        self.assertNotEqual(_card_key("GPLv2"), _card_key("GPLv3"))

    def test_reference_checks_are_topic_scoped_and_traceable(self):
        self.assertEqual(reference_checks("ls -a muestra archivos ocultos"), [])
        checks = reference_checks("GPLv2, FSF y BSD. Python es interpretado y no se compila.")
        self.assertEqual(len(checks), 3)
        self.assertTrue(all(item["url"].startswith("https://") for item in checks))

    def test_heading_normalization_preserves_fenced_examples(self):
        source = "## Contexto Inicial\nContexto.\n## Apuntes de Clase\n### 1. Tema\n```markdown\n## Contexto Inicial\n```"
        result = normalize_body_headings(source)
        validate_body_markdown(result)
        self.assertIn("```markdown\n## Contexto Inicial\n```", result)

    def test_reuses_only_exact_real_vectors_and_batches_unique_new_text(self):
        vector = [0.1] * 1024
        with patch("app.knowledge.embed_texts", return_value=([vector], [False])) as embed:
            vectors, dummies = embed_with_cache(["unchanged", "new", "new"], {"unchanged": vector})
        embed.assert_called_once_with(["new"])
        self.assertEqual(len(vectors), 3)
        self.assertEqual(dummies, [False, False, False])

    def test_long_markdown_sections_are_indexed_without_discarding_the_end(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = []
        note = SimpleNamespace(course_name="Course", class_title="Class")
        processed = SimpleNamespace(id="id", structured_markdown="## Long section\n" + "content " * 1000 + "UNIQUE END MARKER")
        def embed(texts):
            return [[0.1] * 1024 for _ in texts], [False] * len(texts)
        with patch("app.knowledge.embed_texts", side_effect=embed) as embeddings:
            _store_embedding(db, processed, note, commit=False)
        contents = [call.args[0].content for call in db.add.call_args_list]
        self.assertTrue(any("UNIQUE END MARKER" in content for content in contents))
        self.assertGreater(len(contents), 1)
        self.assertEqual(embeddings.call_count, 1)
        db.commit.assert_not_called()

    def test_runtime_disables_nested_retries_and_records_usage(self):
        resolved = llm_models.resolve_model("synthesis", "google/gemini-3.8-flash", environ={"OPENROUTER_API_KEY": "test"})
        response = SimpleNamespace(content="Text", response_metadata={"finish_reason": "stop"}, usage_metadata={"input_tokens": 20, "output_tokens": 10})
        model = streaming_model(response)
        metrics = {}
        with patch("app.generation_runtime.llm_models.create_chat_model", return_value=model) as create:
            self.assertEqual(GenerationClient(resolved, "test", metrics=metrics).invoke("Text").content, response.content)
        self.assertEqual(create.call_args.kwargs["max_retries"], 0)
        self.assertEqual(create.call_args.kwargs["extra_body"]["reasoning"], {"effort": "low", "exclude": True})
        self.assertEqual(metrics["input_tokens"], 20)

    def test_truncated_response_is_not_treated_as_a_complete_note(self):
        resolved = llm_models.resolve_model("synthesis", "google/gemini-3.8-flash", environ={"OPENROUTER_API_KEY": "test"})
        model = streaming_model(SimpleNamespace(content="Incomplete", response_metadata={"finish_reason": "length"}))
        with patch("app.generation_runtime.llm_models.create_chat_model", return_value=model):
            with self.assertRaisesRegex(ValueError, "incompleto"):
                GenerationClient(resolved, "test").invoke("Text")

    def test_timeout_uses_one_auxiliary_fallback_without_changing_user_setting(self):
        resolved = llm_models.resolve_model("query_expansion", "deepseek/deepseek-v4-flash-0731", environ={"OPENROUTER_API_KEY": "test"})
        response = SimpleNamespace(content="{}")
        metrics = {}
        with patch.dict("app.generation_runtime._unavailable_until", {}, clear=True), patch.dict("os.environ", {"OPENROUTER_API_KEY": "test"}), patch.object(GenerationClient, "_invoke_once", side_effect=[GenerationTimeout("timeout"), response]) as invoke:
            client = GenerationClient(resolved, "evidence", metrics=metrics)
            self.assertEqual(client.invoke("Text"), response)
            self.assertEqual(invoke.call_count, 2)
            self.assertEqual(client.resolved.model_id, "google/gemini-3.5-flash-lite")
            self.assertEqual(resolved.model_id, "deepseek/deepseek-v4-flash-0731")
            self.assertTrue(metrics["auxiliary_fallback"])

    def test_reasoning_policy_matches_effective_model_not_just_role(self):
        cases = [
            ("query_expansion", "deepseek/deepseek-v4-flash-0731", {"enabled": False}),
            ("query_expansion", "google/gemini-3.5-flash-lite", {"effort": "minimal", "exclude": True}),
            *[("synthesis", option["id"], {"effort": "low", "exclude": True})
              for option in llm_models.MODEL_CATALOG["synthesis"]],
        ]
        response = SimpleNamespace(content="{}")
        with patch.dict("app.generation_runtime._unavailable_until", {}, clear=True), patch("app.generation_runtime._reasoning_required", set()):
            for role, model_id, expected in cases:
                with self.subTest(role=role, model_id=model_id):
                    resolved = llm_models.resolve_model(role, model_id, environ={"OPENROUTER_API_KEY": "test"})
                    model = streaming_model(response)
                    with patch("app.generation_runtime.llm_models.create_chat_model", return_value=model) as create:
                        GenerationClient(resolved, "test").invoke("Text")
                    self.assertEqual(create.call_args.kwargs["extra_body"]["reasoning"], expected)

    def test_timeout_and_circuit_fallback_both_use_valid_lite_reasoning(self):
        resolved = llm_models.resolve_model("query_expansion", "deepseek/deepseek-v4-flash-0731", environ={"OPENROUTER_API_KEY": "test"})
        response = SimpleNamespace(content="{}")
        primary = streaming_model(GenerationTimeout("timeout"))
        alternate = streaming_model(response, response)
        metrics = {}
        with patch.dict("app.generation_runtime._unavailable_until", {}, clear=True), patch("app.generation_runtime._reasoning_required", set()), patch.dict("os.environ", {"OPENROUTER_API_KEY": "test"}), patch("app.generation_runtime.llm_models.create_chat_model", side_effect=[primary, alternate, alternate]) as create:
            self.assertEqual(GenerationClient(resolved, "glossary", metrics=metrics).invoke("Text").content, response.content)
            # The next class starts while DeepSeek's circuit is still open.
            self.assertEqual(GenerationClient(resolved, "evidence", metrics=metrics).invoke("Text").content, response.content)
        options = [call.kwargs["extra_body"]["reasoning"] for call in create.call_args_list]
        self.assertEqual(options, [{"enabled": False}, {"effort": "minimal", "exclude": True}, {"effort": "minimal", "exclude": True}])
        self.assertEqual(primary.astream.call_count, 1)
        self.assertEqual(alternate.astream.call_count, 2)
        self.assertEqual(metrics["llm_calls"], 3)
        self.assertEqual(metrics["auxiliary_model_effective"], "google/gemini-3.5-flash-lite")
        self.assertEqual(resolved.model_id, "deepseek/deepseek-v4-flash-0731")

    def bad_request(self, message):
        return BadRequestError(message, response=httpx.Response(400, request=httpx.Request("POST", "https://example.test/chat")), body={"error": {"message": message}})

    def test_changed_endpoint_reasoning_requirement_is_repaired_once_and_remembered(self):
        resolved = llm_models.resolve_model("query_expansion", "deepseek/deepseek-v4-flash-0731", environ={"OPENROUTER_API_KEY": "test"})
        response = SimpleNamespace(content="{}")
        error = self.bad_request("Reasoning is mandatory for this endpoint and cannot be disabled.")
        model = streaming_model(error, response, response)
        metrics = {}
        with patch.dict("app.generation_runtime._unavailable_until", {}, clear=True), patch("app.generation_runtime._reasoning_required", set()), patch("app.generation_runtime.llm_models.create_chat_model", return_value=model) as create:
            client = GenerationClient(resolved, "evidence", metrics=metrics)
            self.assertEqual(client.invoke("Text").content, response.content)
            self.assertEqual(GenerationClient(resolved, "glossary", metrics=metrics).invoke("Text").content, response.content)
        options = [call.kwargs["extra_body"]["reasoning"] for call in create.call_args_list]
        self.assertEqual(options, [{"enabled": False}, {"effort": "low", "exclude": True}, {"effort": "low", "exclude": True}])
        self.assertEqual(metrics["reasoning_adjustments"], 1)
        self.assertEqual(metrics["llm_calls"], 3)

    def test_reasoning_compatibility_retry_is_bounded(self):
        resolved = llm_models.resolve_model("query_expansion", "deepseek/deepseek-v4-flash-0731", environ={"OPENROUTER_API_KEY": "test"})
        error = self.bad_request("Reasoning is mandatory for this endpoint and cannot be disabled.")
        model = streaming_model(error, error)
        with patch.dict("app.generation_runtime._unavailable_until", {}, clear=True), patch("app.generation_runtime._reasoning_required", set()), patch("app.generation_runtime.llm_models.create_chat_model", return_value=model):
            with self.assertRaises(BadRequestError):
                GenerationClient(resolved, "evidence").invoke("Text")
        self.assertEqual(model.astream.call_count, 2)

    def test_unrelated_bad_request_is_not_retried(self):
        resolved = llm_models.resolve_model("query_expansion", "deepseek/deepseek-v4-flash-0731", environ={"OPENROUTER_API_KEY": "test"})
        model = streaming_model(self.bad_request("Invalid response schema."))
        with patch.dict("app.generation_runtime._unavailable_until", {}, clear=True), patch("app.generation_runtime._reasoning_required", set()), patch("app.generation_runtime.llm_models.create_chat_model", return_value=model):
            with self.assertRaises(BadRequestError):
                GenerationClient(resolved, "evidence").invoke("Text")
        model.astream.assert_called_once()


class GenerationBudgetTests(unittest.TestCase):
    def test_budgets_depend_on_task_input_size_and_output_capacity(self):
        self.assertEqual(request_budget("glossary", 1000, 4096).total, 150)
        self.assertEqual(request_budget("glossary", 16000, 4096).total, 165)
        self.assertEqual(request_budget("glossary", 32000, 4096).total, 180)
        self.assertEqual(request_budget("flashcards", 32000, 4096).total, 135)
        self.assertEqual(request_budget("evidence", 16000, 6144).total, 105)
        self.assertEqual(request_budget("content", 1000000, 10000).total, 240)
        self.assertGreater(request_budget("flashcards", 1000, 8192).total, request_budget("flashcards", 1000, 4096).total)
        self.assertLessEqual(request_budget("glossary", 1000000, 1000000).total, 180)

    def test_explicit_deadlines_remain_available_for_opt_in_probes(self):
        budget = request_budget("glossary", 50000, 4096, deadline=30)
        self.assertEqual(budget, RequestBudget(30, 30, 30))
        for invalid in (0, -1, float("inf"), float("nan")):
            with self.assertRaises(ValueError):
                request_budget("glossary", 1000, 4096, deadline=invalid)


class GenerationStreamingTests(unittest.TestCase):
    def setUp(self):
        self.resolved = llm_models.resolve_model("synthesis", "google/gemini-3.8-flash", environ={"OPENROUTER_API_KEY": "test"})

    def invoke_stream(self, stream, *, budget=None, metrics=None, progress=None):
        model = SimpleNamespace(astream=MagicMock(side_effect=lambda *_a, **_k: stream()))
        with patch("app.generation_runtime.llm_models.create_chat_model", return_value=model), patch("app.generation_runtime.request_budget", return_value=budget or RequestBudget(0.5, 0.3, 0.1)):
            return GenerationClient(self.resolved, "glossary", metrics=metrics, progress=progress).invoke("private source text")

    def test_complete_json_is_assembled_before_validation_and_usage_is_not_doubled(self):
        usage = {"input_tokens": 12, "output_tokens": 5, "total_tokens": 17}
        async def stream():
            yield AIMessageChunk(content="")
            yield AIMessageChunk(content='{"ok":')
            yield AIMessageChunk(content="true}", response_metadata={"finish_reason": "stop"}, usage_metadata=usage)
            yield AIMessageChunk(content="", response_metadata={"finish_reason": "stop"}, usage_metadata=usage)
        metrics, updates = {}, []
        response = self.invoke_stream(stream, metrics=metrics, progress=updates.append)
        self.assertEqual(json.loads(response.content), {"ok": True})
        self.assertEqual(response.response_metadata["finish_reason"], "stop")
        self.assertEqual(metrics["input_tokens"], 12)
        self.assertEqual(metrics["output_tokens"], 5)
        record = metrics["llm_requests"][0]
        self.assertEqual(record["status"], "complete")
        self.assertEqual(record["output_chars"], len(response.content))
        self.assertEqual(record["chunks"], 2)
        self.assertIn("first_token_ms", record)
        self.assertEqual(updates[0]["llm_requests"][0]["status"], "waiting")
        self.assertEqual(updates[-1]["llm_requests"][0]["status"], "complete")
        self.assertNotIn("private source text", json.dumps(metrics))
        self.assertNotIn(response.content, json.dumps(metrics))

    def test_read_timeout_no_longer_undercuts_the_first_response_budget(self):
        response = SimpleNamespace(content="{}")
        with patch("app.generation_runtime.llm_models.create_chat_model", return_value=streaming_model(response)) as create:
            GenerationClient(self.resolved, "glossary").invoke("a" * 32000)
        self.assertEqual(create.call_args.kwargs["timeout"].read, 144)
        self.assertEqual(create.call_args.kwargs["timeout"].connect, 15)

    def test_schema_stream_uses_standard_usage_frames_without_beta_parsing(self):
        schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"], "additionalProperties": False}
        usage = {"input_tokens": 12, "output_tokens": 5, "total_tokens": 17}
        model = streaming_model(SimpleNamespace(content='{"ok":true}', usage_metadata=usage))
        metrics = {}
        with patch("app.generation_runtime.llm_models.create_chat_model", return_value=model) as create:
            response = GenerationClient(self.resolved, "glossary", schema=schema, metrics=metrics).invoke("source")
        self.assertEqual(json.loads(response.content), {"ok": True})
        self.assertEqual(create.call_args.kwargs["extra_body"]["response_format"]["json_schema"]["schema"], schema)
        model.bind.assert_not_called()
        model.astream.assert_called_once_with("source", stream_usage=True)
        self.assertEqual(metrics["input_tokens"], 12)
        self.assertEqual(metrics["output_tokens"], 5)

    def test_request_history_is_bounded_without_losing_current_call(self):
        model = streaming_model(SimpleNamespace(content="OK"))
        metrics = {"llm_requests": [{"id": str(index), "status": "complete"} for index in range(80)]}
        with patch("app.generation_runtime.llm_models.create_chat_model", return_value=model):
            GenerationClient(self.resolved, "glossary", metrics=metrics).invoke("source")
        self.assertEqual(len(metrics["llm_requests"]), 64)
        self.assertEqual(metrics["llm_requests"][-1]["status"], "complete")

    def test_parallel_requests_keep_independent_progress_and_combined_usage(self):
        usage = {"input_tokens": 12, "output_tokens": 5, "total_tokens": 17}
        async def stream():
            yield AIMessageChunk(content="first")
            await asyncio.sleep(0.01)
            yield AIMessageChunk(content="last", response_metadata={"finish_reason": "stop"}, usage_metadata=usage)
        model = SimpleNamespace(astream=MagicMock(side_effect=lambda *_a, **_k: stream()))
        metrics, updates = {}, []
        def run(phase):
            return GenerationClient(self.resolved, phase, metrics=metrics, progress=updates.append).invoke("source")
        with patch("app.generation_runtime.llm_models.create_chat_model", return_value=model), ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(executor.map(run, ["glossary", "flashcards"]))
        self.assertEqual([response.content for response in responses], ["firstlast", "firstlast"])
        self.assertEqual({record["phase"] for record in metrics["llm_requests"]}, {"glossary", "flashcards"})
        self.assertTrue(all(record["status"] == "complete" for record in metrics["llm_requests"]))
        self.assertEqual(metrics["input_tokens"], 24)
        self.assertEqual(metrics["output_tokens"], 10)
        self.assertTrue(any(len(update["llm_requests"]) == 2 for update in updates))

    def test_empty_events_do_not_reset_first_content_timer(self):
        closed = []
        async def stream():
            try:
                while True:
                    yield AIMessageChunk(content="")
                    await asyncio.sleep(0.002)
            finally:
                closed.append(True)
        metrics = {}
        with self.assertRaises(GenerationTimeout) as raised:
            self.invoke_stream(stream, budget=RequestBudget(0.3, 0.015, 0.03), metrics=metrics)
        self.assertEqual(raised.exception.kind, "first_response")
        self.assertEqual(metrics["llm_requests"][0]["timeout_kind"], "first_response")
        self.assertNotIn("first_token_ms", metrics["llm_requests"][0])
        self.assertEqual(closed, [True])

    def test_output_stall_is_distinct_from_waiting_for_first_content(self):
        async def stream():
            yield AIMessageChunk(content="partial")
            await asyncio.sleep(0.1)
        metrics = {}
        with self.assertRaises(GenerationTimeout) as raised:
            self.invoke_stream(stream, budget=RequestBudget(0.3, 0.2, 0.015), metrics=metrics)
        self.assertEqual(raised.exception.kind, "idle")
        record = metrics["llm_requests"][0]
        self.assertEqual(record["output_chars"], 7)
        self.assertEqual(record["status"], "timeout")

    def test_continuous_progress_does_not_disable_total_deadline(self):
        closed = []
        async def stream():
            try:
                while True:
                    yield AIMessageChunk(content="a")
                    await asyncio.sleep(0.002)
            finally:
                closed.append(True)
        metrics = {}
        with self.assertRaises(GenerationTimeout) as raised:
            self.invoke_stream(stream, budget=RequestBudget(0.03, 0.02, 0.02), metrics=metrics)
        self.assertEqual(raised.exception.kind, "total")
        self.assertGreater(metrics["llm_requests"][0]["output_chars"], 0)
        self.assertEqual(closed, [True])

    def test_slow_but_advancing_stream_can_complete(self):
        async def stream():
            await asyncio.sleep(0.025)
            yield AIMessageChunk(content="a")
            await asyncio.sleep(0.025)
            yield AIMessageChunk(content="b", response_metadata={"finish_reason": "stop"})
        response = self.invoke_stream(stream, budget=RequestBudget(0.2, 0.1, 0.1))
        self.assertEqual(response.content, "ab")

    def test_eof_without_terminal_confirmation_is_not_accepted(self):
        async def stream():
            yield AIMessageChunk(content='{"ok":true}')
        with self.assertRaises(GenerationStreamError):
            self.invoke_stream(stream)

    def test_midstream_error_does_not_return_partial_output(self):
        async def stream():
            yield AIMessageChunk(content="partial")
            yield AIMessageChunk(content="", response_metadata={"finish_reason": "error"})
        with self.assertRaises(GenerationStreamError):
            self.invoke_stream(stream)

    def test_failure_of_progress_reporting_does_not_discard_valid_output(self):
        async def stream():
            yield AIMessageChunk(content="OK", response_metadata={"finish_reason": "stop"})
        progress = MagicMock(side_effect=RuntimeError("temporarily unavailable tracking"))
        self.assertEqual(self.invoke_stream(stream, progress=progress).content, "OK")
        self.assertGreater(progress.call_count, 1)


if __name__ == "__main__":
    unittest.main()
