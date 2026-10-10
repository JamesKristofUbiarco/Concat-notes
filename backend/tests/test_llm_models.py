import os
import sys
import unittest
from unittest.mock import patch


BACKEND_ROOT = os.path.dirname(os.path.dirname(__file__))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app import llm_models


class LlmModelResolutionTests(unittest.TestCase):
    def test_deepseek_v4_vision_is_available_for_vision_roles(self):
        option = llm_models.get_model_definition("synthesis", "deepseek/deepseek-v4-flash-vision-exp")
        self.assertIsNotNone(option)
        self.assertEqual(option["name"], "DeepSeek V4 Flash Vision Experimental")
        self.assertEqual(option["transport"], llm_models.OPENROUTER_TRANSPORT)
        self.assertIn("structured_output", option["capabilities"])

        resolved = llm_models.resolve_model(
            "synthesis",
            "deepseek/deepseek-v4-flash-vision-exp",
            environ={"OPENROUTER_API_KEY": "configured"},
            allow_fallback=False,
        )
        self.assertEqual(resolved.api_model_id, "deepseek/deepseek-v4-flash-vision-exp")
        self.assertFalse(resolved.fallback_used)

    def test_new_vision_models_are_available_for_vision_roles(self):
        for role in ("synthesis", "image_analysis", "document_vision"):
            option = llm_models.get_model_definition(role, "qwen/qwen3.8-flash")
            self.assertIsNotNone(option)
            self.assertEqual(option["transport"], llm_models.OPENROUTER_TRANSPORT)

        vision_option = llm_models.get_model_definition("image_analysis", "qwen/qwen3.8-flash")
        self.assertIn("vision", vision_option["capabilities"])

    def test_gemini_selection_uses_openrouter_transport(self):
        resolved = llm_models.resolve_model(
            "synthesis",
            "google/gemini-3.8-flash",
            environ={"OPENROUTER_API_KEY": "configured"},
        )
        self.assertEqual(resolved.transport, llm_models.OPENROUTER_TRANSPORT)
        self.assertEqual(resolved.required_env, "OPENROUTER_API_KEY")
        self.assertEqual(resolved.api_model_id, "google/gemini-3.8-flash")
        self.assertFalse(resolved.fallback_used)

    def test_all_gemini_roles_use_openrouter(self):
        expected = {
            ("synthesis", "google/gemini-3.8-flash"),
            ("query_expansion", "google/gemini-3.5-flash-lite"),
            ("image_analysis", "google/gemini-3.8-flash"),
            ("document_vision", "google/gemini-3.8-flash"),
        }
        for role, model_id in expected:
            option = llm_models.get_model_definition(role, model_id)
            self.assertIsNotNone(option)
            self.assertEqual(option["transport"], llm_models.OPENROUTER_TRANSPORT)
            self.assertEqual(option["required_env"], "OPENROUTER_API_KEY")

    def test_legacy_image_model_id_falls_back_and_is_not_available(self):
        resolved = llm_models.resolve_model(
            "image_analysis",
            "gemini-3.6-flash",
            environ={"OPENROUTER_API_KEY": "configured"},
            allow_fallback=True,
        )
        self.assertEqual(resolved.model_id, "google/gemini-3.8-flash")
        self.assertEqual(resolved.api_model_id, "google/gemini-3.8-flash")
        self.assertEqual(resolved.transport, llm_models.OPENROUTER_TRANSPORT)

    def test_openrouter_model_cannot_be_selected_without_openrouter_key(self):
        with self.assertRaises(llm_models.ModelResolutionError):
            llm_models.resolve_model(
                "query_expansion",
                "qwen/qwen3.8-flash",
                environ={"GOOGLE_API_KEY": "configured"},
                allow_fallback=False,
            )

    def test_missing_selected_provider_uses_explicit_fallback(self):
        resolved = llm_models.resolve_model(
            "query_expansion",
            "model-that-is-no-longer-in-catalog",
            environ={"OPENROUTER_API_KEY": "configured"},
        )
        self.assertEqual(resolved.model_id, "deepseek/deepseek-v4-flash-0731")
        self.assertTrue(resolved.fallback_used)
        self.assertIn("catálogo", resolved.fallback_reason)

    def test_public_catalog_exposes_readiness_without_secret_names_or_values(self):
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "super-secret-value"}, clear=True):
            catalog = llm_models.public_catalog()

        qwen = next(item for item in catalog["synthesis"] if item["id"] == "qwen/qwen3.8-flash")
        self.assertTrue(qwen["configured"])
        self.assertNotIn("required_env", qwen)
        self.assertNotIn("api_model_id", qwen)
        self.assertNotIn("super-secret-value", repr(catalog))

    def test_catalog_records_mandatory_reasoning_for_gemini_lite(self):
        option = llm_models.get_model_definition("query_expansion", "google/gemini-3.5-flash-lite")
        self.assertTrue(option["reasoning"]["mandatory"])
        self.assertIn("minimal", option["reasoning"]["supported_efforts"])
        for model_id in ("google/gemini-3.8-flash", "z-ai/glm-5.3-flash"):
            self.assertTrue(llm_models.get_model_definition("synthesis", model_id)["reasoning"]["mandatory"])


if __name__ == "__main__":
    unittest.main()
