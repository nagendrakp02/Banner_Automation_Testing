
async def health_response() -> dict:
    """
    Returns system health including which vision model is active
    and whether it is pulled and ready.
    """
    from backend.services.vision_client import vision_client
    from backend.core.config import settings

    available   = await vision_client.is_available()
    vision_models = await vision_client.list_vision_models()

    return {
        "status":         "ok",
        "version":        settings.app_version,
        "vision_model":   settings.ollama_vision_model,
        "vision_ready":   available,
        "vision_models_pulled": vision_models,
        "ollama_url":     settings.ollama_base_url,
        "note": (
            "ready" if available
            else f"Model '{settings.ollama_vision_model}' not pulled. "
                 f"Run: ollama pull {settings.ollama_vision_model}"
        ),
    }