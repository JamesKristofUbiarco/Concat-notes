"""Catálogo y resolución explícita de los modelos LLM de la aplicación.

La selección persistida identifica un modelo lógico. Este módulo determina el
transporte real (OpenRouter o, para futuras integraciones, Google AI Studio),
valida sus credenciales y deja registrado cualquier fallback aplicado. Ninguna
API key se expone al cliente.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import os
from typing import Mapping, Optional


logger = logging.getLogger("llm_models")

GOOGLE_TRANSPORT = "google_ai_studio"
OPENROUTER_TRANSPORT = "openrouter"

TRANSPORT_LABELS = {
    GOOGLE_TRANSPORT: "Google AI Studio",
    OPENROUTER_TRANSPORT: "OpenRouter",
}

DEFAULT_MODELS = {
    "synthesis": "google/gemini-3.8-flash",
    "query_expansion": "deepseek/deepseek-v4-flash-0731",
    "image_analysis": "google/gemini-3.8-flash",
    "document_vision": "google/gemini-3.8-flash",
}

def _model(
    model_id: str,
    name: str,
    provider: str,
    transport: str,
    api_model_id: str,
    capabilities: list[str],
) -> dict:
    required_env = "GOOGLE_API_KEY" if transport == GOOGLE_TRANSPORT else "OPENROUTER_API_KEY"
    return {
        "id": model_id,
        "name": name,
        "provider": provider,
        "transport": transport,
        "transport_label": TRANSPORT_LABELS[transport],
        "api_model_id": api_model_id,
        "required_env": required_env,
        "capabilities": capabilities,
    }


GOOGLE_38_FLASH = _model(
    "google/gemini-3.8-flash", "Gemini 3.8 Flash", "Google", OPENROUTER_TRANSPORT,
    "google/gemini-3.8-flash", ["text", "vision", "structured_output"],
)
QWEN_38_FLASH = _model(
    "qwen/qwen3.8-flash", "Qwen3.8 Flash", "Qwen", OPENROUTER_TRANSPORT,
    "qwen/qwen3.8-flash", ["text", "vision", "structured_output"],
)
GLM_53_FLASH = _model(
    "z-ai/glm-5.3-flash", "GLM 5.3 Flash", "Z.ai", OPENROUTER_TRANSPORT,
    "z-ai/glm-5.3-flash", ["text", "vision", "structured_output"],
)
DEEPSEEK_4_VISION = _model(
    "deepseek/deepseek-v4-flash-vision-exp", "DeepSeek V4 Flash Vision Experimental", "DeepSeek", OPENROUTER_TRANSPORT,
    "deepseek/deepseek-v4-flash-vision-exp", ["text", "vision", "structured_output"],
)
DEEPSEEK_4_AUX = _model(
    "deepseek/deepseek-v4-flash-0731", "DeepSeek V4 Flash 0731", "DeepSeek", OPENROUTER_TRANSPORT,
    "deepseek/deepseek-v4-flash-0731", ["text", "structured_output"],
)
GEMINI_35_LITE = _model(
    "google/gemini-3.5-flash-lite", "Gemini 3.5 Flash Lite", "Google", OPENROUTER_TRANSPORT,
    "google/gemini-3.5-flash-lite", ["text", "vision"],
)

VISION_MODELS = [GOOGLE_38_FLASH, QWEN_38_FLASH, GLM_53_FLASH, DEEPSEEK_4_VISION]

MODEL_CATALOG = {
    "synthesis": [option.copy() for option in VISION_MODELS],
    "query_expansion": [DEEPSEEK_4_AUX.copy(), GEMINI_35_LITE.copy()],
    "image_analysis": [option.copy() for option in VISION_MODELS],
}

"""The same vision-capable set is available for document image analysis."""
MODEL_CATALOG["document_vision"] = [option.copy() for option in VISION_MODELS]


def normalize_model_id(role: str, model_id: str) -> str:
    # Old persisted choices are intentionally not aliased: they must fall back
    # to the configured model in the current catalog and never appear in UI.
    return model_id


class ModelResolutionError(RuntimeError):
    """No hay un modelo ejecutable para el rol solicitado."""


@dataclass(frozen=True)
class ResolvedModel:
    role: str
    requested_model: str
    model_id: str
    api_model_id: str
    name: str
    provider: str
    transport: str
    required_env: str
    fallback_used: bool = False
    fallback_reason: Optional[str] = None

    def public_dict(self) -> dict:
        return {
            "role": self.role,
            "requested_model": self.requested_model,
            "effective_model": self.model_id,
            "name": self.name,
            "provider": self.provider,
            "transport": self.transport,
            "transport_label": TRANSPORT_LABELS[self.transport],
            "fallback_used": self.fallback_used,
            "fallback_reason": self.fallback_reason,
        }


def get_model_definition(role: str, model_id: str) -> Optional[dict]:
    return next((item for item in MODEL_CATALOG.get(role, []) if item["id"] == model_id), None)


def model_is_configured(model: dict, environ: Optional[Mapping[str, str]] = None) -> bool:
    env = os.environ if environ is None else environ
    return bool(env.get(model["required_env"]))


def public_catalog(environ: Optional[Mapping[str, str]] = None) -> dict:
    result: dict[str, list[dict]] = {}
    for role, options in MODEL_CATALOG.items():
        result[role] = []
        for option in options:
            configured = model_is_configured(option, environ)
            result[role].append(
                {
                    key: value
                    for key, value in option.items()
                    if key not in {"api_model_id", "required_env"}
                }
                | {
                    "configured": configured,
                    "unavailable_reason": None
                    if configured
                    else f"Falta configurar {option['required_env']}.",
                }
            )
    return result


def resolve_model(
    role: str,
    requested_model: str,
    *,
    environ: Optional[Mapping[str, str]] = None,
    allow_fallback: bool = True,
) -> ResolvedModel:
    if role not in MODEL_CATALOG:
        raise ModelResolutionError(f"Rol de modelo desconocido: {role}")

    requested_model = normalize_model_id(role, requested_model)
    requested_definition = get_model_definition(role, requested_model)
    if requested_definition and model_is_configured(requested_definition, environ):
        selected = requested_definition
        fallback_reason = None
    else:
        if requested_definition:
            fallback_reason = f"Falta configurar {requested_definition['required_env']}."
        else:
            fallback_reason = "El modelo guardado ya no pertenece al catálogo."

        if not allow_fallback:
            raise ModelResolutionError(fallback_reason)

        selected = next(
            (option for option in MODEL_CATALOG[role] if model_is_configured(option, environ)),
            None,
        )
        if selected is None:
            raise ModelResolutionError(
                f"No hay credenciales configuradas para ningún modelo del rol '{role}'."
            )

    resolved = ResolvedModel(
        role=role,
        requested_model=requested_model,
        model_id=selected["id"],
        api_model_id=selected["api_model_id"],
        name=selected["name"],
        provider=selected["provider"],
        transport=selected["transport"],
        required_env=selected["required_env"],
        fallback_used=selected["id"] != requested_model,
        fallback_reason=fallback_reason,
    )
    logger.info(
        "Resolución LLM role=%s requested=%s effective=%s transport=%s fallback=%s reason=%s",
        role,
        requested_model,
        resolved.model_id,
        resolved.transport,
        resolved.fallback_used,
        resolved.fallback_reason or "none",
    )
    return resolved


def resolve_selected_model(db, role: str, *, allow_fallback: bool = True) -> ResolvedModel:
    from app import crud

    requested_model = crud.get_model_setting(db, role)
    return resolve_model(role, requested_model, allow_fallback=allow_fallback)


def create_chat_model(resolved: ResolvedModel, *, timeout: int, max_retries: int, max_tokens: Optional[int] = None):
    api_key = os.getenv(resolved.required_env)
    if not api_key:
        raise ModelResolutionError(f"Falta configurar {resolved.required_env}.")

    if resolved.transport == OPENROUTER_TRANSPORT:
        from langchain_openai import ChatOpenAI

        kwargs = {"max_tokens": max_tokens} if max_tokens else {}
        return ChatOpenAI(
            model=resolved.api_model_id,
            openai_api_key=api_key,
            openai_api_base="https://openrouter.ai/api/v1",
            default_headers={
                "HTTP-Referer": "https://github.com/JamesKristofUbiarco/Concat-notes",
                "X-Title": "Gestor Inteligente de Notas",
            },
            timeout=timeout,
            max_retries=max_retries,
            **kwargs,
        )

    if resolved.transport == GOOGLE_TRANSPORT:
        from langchain_google_genai import ChatGoogleGenerativeAI

        kwargs = {"max_output_tokens": max_tokens} if max_tokens else {}
        return ChatGoogleGenerativeAI(
            model=resolved.api_model_id,
            google_api_key=api_key,
            timeout=timeout,
            max_retries=max_retries,
            **kwargs,
        )

    raise ModelResolutionError(f"Transporte no soportado: {resolved.transport}")


def model_settings_payload(db) -> dict:
    from app import crud

    selected = {
        role: normalize_model_id(role, crud.get_model_setting(db, role))
        for role in MODEL_CATALOG
    }
    effective = {}
    for role, requested_model in selected.items():
        try:
            effective[role] = resolve_model(role, requested_model).public_dict()
        except ModelResolutionError as exc:
            effective[role] = {
                "role": role,
                "requested_model": requested_model,
                "effective_model": None,
                "name": None,
                "provider": None,
                "transport": None,
                "transport_label": None,
                "fallback_used": False,
                "fallback_reason": str(exc),
            }

    return selected | {"available": public_catalog(), "effective": effective}
