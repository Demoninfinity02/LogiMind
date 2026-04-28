from __future__ import annotations

import json
from urllib import error, request

from django.conf import settings


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


def get_gemma_explanation(context: dict) -> str:
    url = getattr(settings, "OLLAMA_URL", "http://localhost:11434/api/generate")
    model = getattr(settings, "OLLAMA_MODEL", "gemma3:latest")
    timeout_s = int(getattr(settings, "OLLAMA_TIMEOUT_SECONDS", 10))
    body = {
        "model": model,
        "prompt": _prompt_for_context(context),
        "stream": False,
    }
    req = request.Request(
        url=url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=timeout_s) as resp:
        raw = resp.read().decode("utf-8")
    data = json.loads(raw)
    text = str(data.get("response", "")).strip()
    if not text:
        raise ValueError("Empty response from Ollama")
    return " ".join(text.split())


def get_gemma_explanation_safe(context: dict) -> str:
    try:
        return get_gemma_explanation(context)
    except (error.URLError, error.HTTPError, TimeoutError, ValueError, json.JSONDecodeError):
        return FALLBACK_EXPLANATION
