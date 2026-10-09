"""Optional AI explanation layer. Core numbers never depend on it.
Set AI_PROVIDER=anthropic|groq|gemini plus the matching key in the environment (backend only)."""
import json
import os

import httpx

SYSTEM = ("You are a business analyst. Explain the findings below in plain language for an executive. "
          "Use ONLY the numbers provided. Do not invent figures or causes. Max 180 words, short paragraphs.")


def status() -> dict:
    prov = _provider()
    return {"enabled": prov is not None, "provider": prov}


def _provider():
    p = os.getenv("AI_PROVIDER", "").lower()
    keys = {"anthropic": "ANTHROPIC_API_KEY", "groq": "GROQ_API_KEY", "gemini": "GEMINI_API_KEY"}
    if p in keys and os.getenv(keys[p]):
        return p
    for name, k in keys.items():   # auto-pick the first configured key
        if os.getenv(k):
            return name
    return None


def explain(summary: dict) -> dict:
    prov = _provider()
    if not prov:
        return {"enabled": False, "text": None,
                "message": "AI explanations are off. Set ANTHROPIC_API_KEY, GROQ_API_KEY or GEMINI_API_KEY on the server to enable them. All numbers in InsightPilot work without it."}
    prompt = "Findings (JSON):\n" + json.dumps(summary, default=str)[:12000]
    try:
        with httpx.Client(timeout=45) as c:
            if prov == "anthropic":
                r = c.post("https://api.anthropic.com/v1/messages", headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"},
                           json={"model": os.getenv("AI_MODEL", "claude-sonnet-5-5"), "max_tokens": 600, "system": SYSTEM, "messages": [{"role": "user", "content": prompt}]})
                r.raise_for_status()
                text = "".join(b.get("text", "") for b in r.json()["content"])
            elif prov == "groq":
                r = c.post("https://api.groq.com/openai/v1/chat/completions", headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"},
                           json={"model": os.getenv("AI_MODEL", "llama-3.3-70b-versatile"), "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]})
                r.raise_for_status()
                text = r.json()["choices"][0]["message"]["content"]
            else:
                model = os.getenv("AI_MODEL", "gemini-2.0-flash")
                r = c.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]},
                           json={"systemInstruction": {"parts": [{"text": SYSTEM}]}, "contents": [{"parts": [{"text": prompt}]}]})
                r.raise_for_status()
                text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        return {"enabled": True, "provider": prov, "text": text.strip()}
    except Exception as e:
        return {"enabled": True, "provider": prov, "text": None, "message": f"The AI provider call failed ({type(e).__name__}). The deterministic analysis is unaffected."}
