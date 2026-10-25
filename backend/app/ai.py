"""Optional AI explanation layer. Core numbers never depend on it.
Set AI_PROVIDER=anthropic|groq|gemini plus the matching key in the environment (backend only)."""
import json
import os
import re

import httpx

SYSTEM = ("You are a business analyst. Answer the user's question using ONLY the dataset context and computed metrics provided. "
          "Do not invent figures or facts. If the data does not support the answer, say that clearly. "
          "Be concise, natural, and cite the relevant numbers when available.")


def status() -> dict:
    prov = _provider()
    return {"enabled": prov is not None, "provider": prov}


def _provider():
    p = os.getenv("AI_PROVIDER", "").lower()
    keys = {"anthropic": "ANTHROPIC_API_KEY", "groq": "GROQ_API_KEY", "gemini": "GEMINI_API_KEY"}
    if p in keys and os.getenv(keys[p]):
        return p
    for name, k in keys.items():
        if os.getenv(k):
            return name
    return None


def _extract_text(payload: dict, provider: str):
    if provider == "anthropic":
        return "".join(block.get("text", "") for block in payload["content"])
    if provider == "groq":
        return payload["choices"][0]["message"]["content"]
    return payload["candidates"][0]["content"]["parts"][0]["text"]


def _build_prompt(question: str, context: dict, history: list | None = None):
    history_text = ""
    if history:
        recent = history[-6:]
        history_text = "\nConversation history:\n" + "\n".join(f"{h.get('role', 'user')}: {h.get('content', '')}" for h in recent)
    payload_json = json.dumps(context, default=str)
    return (
        f"{SYSTEM}\n\n"
        f"{history_text}\n\n"
        f"Question: {question}\n\n"
        "Dataset context (JSON):\n"
        f"{payload_json[:18000]}\n\n"
        "Answer directly in plain language. If a number is relevant, state it. If the dataset does not contain the required information, say so clearly instead of guessing."
    )


def answer_question(question: str, context: dict, history: list | None = None) -> dict:
    q = (question or "").strip()
    if not q:
        return {"enabled": False, "answer": None, "evidence": context.get("evidence", []), "message": "Please enter a question for the AI analyst."}

    provider = _provider()
    if not provider:
        return {"enabled": False, "answer": None, "evidence": context.get("evidence", []),
                "message": "AI chat is not configured. Set GEMINI_API_KEY, GROQ_API_KEY, or ANTHROPIC_API_KEY on the backend to enable dataset-grounded answers."}

    prompt = _build_prompt(q, context, history)
    try:
        with httpx.Client(timeout=45) as client:
            if provider == "anthropic":
                response = client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"},
                    json={
                        "model": os.getenv("AI_MODEL", "claude-sonnet-4-20250514"),
                        "max_tokens": 600,
                        "system": SYSTEM,
                        "messages": [{"role": "user", "content": prompt}],
                    },
                )
                response.raise_for_status()
                text = _extract_text(response.json(), provider)
            elif provider == "groq":
                response = client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"},
                    json={
                        "model": os.getenv("AI_MODEL", "llama-3.3-70b-versatile"),
                        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
                    },
                )
                response.raise_for_status()
                text = _extract_text(response.json(), provider)
            else:
                model = os.getenv("AI_MODEL", "gemini-2.0-flash")
                response = client.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                    headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]},
                    json={"systemInstruction": {"parts": [{"text": SYSTEM}]}, "contents": [{"parts": [{"text": prompt}]}]},
                )
                response.raise_for_status()
                text = _extract_text(response.json(), provider)

        clean_text = re.sub(r"\s+", " ", text).strip()
        return {"enabled": True, "provider": provider, "answer": clean_text, "evidence": context.get("evidence", []), "message": None}
    except Exception as exc:
        return {"enabled": True, "provider": provider, "answer": None, "evidence": context.get("evidence", []),
                "message": f"The AI provider call failed ({type(exc).__name__}). The dataset analysis remains available on the dashboard, but the live AI answer could not be generated right now."}
