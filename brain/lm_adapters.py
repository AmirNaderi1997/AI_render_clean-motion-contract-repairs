"""Wire-format adapters. No arbitrary URL, shell, or model-produced code execution."""
from __future__ import annotations

PATHS = {"chat": "chat/completions", "responses": "responses", "messages": "messages", "embeddings": "embeddings",
         "image": "images/generations", "speech": "audio/speech", "transcription": "audio/transcriptions", "video": "videos/generations"}


def payload(endpoint, model, messages, *, tokens=4096, temperature=None, stream=False, extra=None):
    data = {"model": model}
    if endpoint == "chat":
        data.update(messages=messages, max_tokens=tokens)
    elif endpoint == "responses":
        data.update(input=messages, max_output_tokens=tokens)
    elif endpoint == "messages":
        data.update(messages=[m for m in messages if m["role"] != "system"], max_tokens=tokens)
        system = [m["content"] for m in messages if m["role"] == "system"]
        if system: data["system"] = "\n".join(system)
    elif endpoint == "embeddings":
        data["input"] = messages
    else:
        raise ValueError("Media endpoints require a separately verified media adapter")
    if endpoint != "embeddings":
        if temperature is not None: data["temperature"] = temperature
        if stream: data["stream"] = True
    if extra: data.update(extra)
    return data


def text(endpoint, data):
    if endpoint == "chat":
        choices = data.get("choices") or []
        value = choices[0].get("message", {}).get("content") if choices else None
        if isinstance(value, str): return value
        if isinstance(value, list): return "".join(p.get("text", "") for p in value if p.get("type") == "text")
    elif endpoint == "responses":
        return data.get("output_text") or "".join(p.get("text", "") for item in data.get("output", [])
                    for p in item.get("content", []) if p.get("type") == "output_text")
    elif endpoint == "messages":
        return "".join(p.get("text", "") for p in data.get("content", []) if p.get("type") == "text")
    return ""


def usage(data):
    value = data.get("usage") or {}
    return {"input_tokens": value.get("prompt_tokens", value.get("input_tokens")),
            "output_tokens": value.get("completion_tokens", value.get("output_tokens")),
            "cost": value.get("cost") if isinstance(value.get("cost"), (int, float)) else None}
