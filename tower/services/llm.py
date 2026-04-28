from __future__ import annotations

import json
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

FALLBACK_EXPLANATION = (
    "Decision explanation is temporarily unavailable. The system continues to use live risk, delay, "
    "and cost constraints to keep this route decision up to date."
)


def _prompt_for_context(context: dict) -> str:
    payload = json.dumps(context, ensure_ascii=True)
    return (
        "You are a logistics decision explainer.\n"
        "Rules:\n"
        "- Use ONLY the provided JSON inputs.\n"
        "- Do NOT invent data.\n"
        "- Keep output to 2-3 short sentences.\n"
        "- If the route is blocked, explicitly mention the constraint.\n"
        "- Keep wording concise and consistent.\n\n"
        f"Input JSON:\n{payload}\n\n"
        "Return only the explanation text."
    )


def get_gemini_explanation(context: dict) -> str:
    """Call the Google Gemini API to generate a logistics decision explanation."""
    api_key = getattr(settings, "GEMINI_API_KEY", "") or ""
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not configured.")

    # Lazy import so the rest of the app works even if the package isn't installed yet.
    try:
        import google.generativeai as genai  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "google-generativeai is not installed. Run: pip install google-generativeai"
        ) from exc

    model_name = getattr(settings, "GEMINI_MODEL", "gemini-1.5-flash")
    timeout_s = int(getattr(settings, "GEMINI_TIMEOUT_SECONDS", 15))

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)

    generation_config = genai.types.GenerationConfig(
        max_output_tokens=256,
        temperature=0.2,
    )

    response = model.generate_content(
        _prompt_for_context(context),
        generation_config=generation_config,
        request_options={"timeout": timeout_s},
    )

    text = (response.text or "").strip()
    if not text:
        raise ValueError("Empty response from Gemini API.")
    return " ".join(text.split())


def get_gemma_explanation_safe(context: dict) -> str:
    """Return a Gemini explanation, or a safe fallback string on any error."""
    try:
        return get_gemini_explanation(context)
    except Exception as exc:
        logger.warning("Gemini explanation failed: %s", exc)
        import traceback
        traceback.print_exc()
        return FALLBACK_EXPLANATION

# Keep the old name as an alias so existing callers don't break.
get_gemma_explanation = get_gemini_explanation
