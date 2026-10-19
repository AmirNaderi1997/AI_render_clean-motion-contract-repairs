"""Task/provider policy for the existing LM gateway.

These are preferences, not proof of capability or production activation. A pair
must be independently registered and tested before the gateway may execute it.
Raw model IDs below were read from the Gateway's registered endpoint models.
"""
from __future__ import annotations

PROVIDERS = {
    "google": {"title": "Google AI Studio", "group": None, "prefix": "google:", "quota": None},
    "jarvis": {"title": "Jarvis", "group": "jarvis-all-models", "quota": None},
    "arvancloud": {"title": "ArvanCloud", "group": "arvancloud-all-models", "quota": None},
    "sarovi": {"title": "Sarovi", "group": "sarovi-all-models", "quota": None},
    "openai": {"title": "OpenAI", "group": "openai-all-models", "quota": None},
}


def qualified_id(provider: str, model_id: str) -> str:
    """Only approved groups; preserve case, punctuation and slashes verbatim."""
    item = PROVIDERS[provider]
    if not model_id or len(model_id) > 400 or "#" in model_id or any(c.isspace() for c in model_id):
        raise ValueError("Invalid registered model ID")
    if model_id.startswith(("custom:", "google:")):
        raise ValueError("Expected the raw registered model ID")
    return f"custom:{model_id}#{item['group']}" if item["group"] else item["prefix"] + model_id


# Cross-provider versions may differ; never pretend Opus 5.5 exists on Arvan.
POWER = [("jarvis", "CLAUDE_OPUS_5_5"), ("arvancloud", "Claude-Opus-4.7")]
STORY = [("jarvis", "CLAUDE_SONNET_5_5"), ("arvancloud", "Claude-Sonnet-4.6")]
LIGHT = [("google", "gemini-3.5-flash"), ("arvancloud", "DeepSeek-V4-Flash"),
         ("arvancloud", "GLM-5.3-Flash"), ("jarvis", "DEEPSEEK_V4_FLASH")]
VISION = [("jarvis", "GPT_5_6_SOL"), ("google", "gemini-3.1-pro-preview"),
          ("arvancloud", "GPT-5.6-Sol")]


def _task(title, capability, pairs, parent):
    return {"title": title, "capability": capability, "parent": parent,
            "preferences": [{"provider": p, "model_id": m, "id": qualified_id(p, m)} for p,m in pairs]}


TASKS = {
    "intent_classification": _task("Intent Classification", "chat", LIGHT, "editing_agent"),
    "general_chat": _task("General Chat", "chat", LIGHT, "general_chat"),
    "edit_planning": _task("Edit Planning", "chat", POWER, "editing_agent"),
    "hyperframes_design": _task("HyperFrames Design", "chat", POWER, "editing_agent"),
    "remotion_design": _task("Remotion Design", "chat", POWER, "editing_agent"),
    "complex_editing_agent": _task("Complex Editing Agent", "chat", POWER, "editing_agent"),
    "storyboard_generation": _task("Storyboard Generation", "chat", STORY, "script"),
    "video_understanding": _task("Video Understanding", "vision", VISION, "video_understanding"),
    "effects_v4_vision": _task("Effects V4 Vision", "vision", VISION, "video_understanding"),
    "visual_qc": _task("Visual QC", "vision", VISION, "video_understanding"),
    "segment_analysis": _task("Segment Analysis", "chat", LIGHT, "editing_agent"),
    "transcript_correction": _task("Transcript Correction", "chat", LIGHT, "subtitles"),
    "translation": _task("Translation", "chat", STORY, "subtitles"),
    "subtitle_formatting": _task("Subtitle Formatting", "chat", LIGHT, "subtitles"),
    "script_generation": _task("Script Generation", "chat", STORY, "script"),
    "image_editing": _task("Image Editing", "image", [("jarvis","GPT_IMAGE_2_5_SUNBURST")], "image"),
    "photorealistic_image": _task("Photorealistic Image", "image", [("jarvis","GPT_IMAGE_2_5_SUNBURST"), ("sarovi","bytedance-seed/seedream-5-0-pro")], "image"),
    "creative_image": _task("Creative Image", "image", [("sarovi","google/gemini-3-pro-image"), ("sarovi","bytedance-seed/seedream-5-0-pro")], "image"),
    "storyboard_image": _task("Storyboard Image", "image", [("jarvis","gemini-3-1-flash-image"), ("sarovi","google/gemini-3.1-flash-image")], "image"),
    "product_video": _task("Product Video", "video", [("sarovi","bytedance/seedance-2.5")], "video"),
    "cinematic_video": _task("Cinematic Video", "video", [("sarovi","openai/sora-2-pro"), ("sarovi","google/veo-3.1")], "video"),
    "fast_broll": _task("Fast B-roll", "video", [("sarovi","bytedance/seedance-2.0-fast"), ("sarovi","google/veo-3.1-fast")], "video"),
    "image_to_video": _task("Image-to-Video", "video", [("sarovi","kwaivgi/kling-v3.0-std"), ("sarovi","bytedance/seedance-2.5")], "video"),
    "narration": _task("Narration / TTS", "speech", [("sarovi","elevenlabs/eleven-v4")], "audio"),
    # No registered Scribe/embedding pair was discovered; do not invent one.
    "transcription": _task("Transcription", "transcription", [], "transcription"),
    "music_generation": _task("Music Generation", "music", [("sarovi","google/lyria-3-clip-preview")], "audio"),
    "embeddings": _task("Embeddings", "embeddings", [], "embeddings"),
}
