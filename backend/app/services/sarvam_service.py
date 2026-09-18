from .provider import ServiceError, post_json

LANGUAGES = {
    "unknown",
    "hi-IN",
    "bn-IN",
    "kn-IN",
    "ml-IN",
    "mr-IN",
    "od-IN",
    "pa-IN",
    "ta-IN",
    "te-IN",
    "en-IN",
    "gu-IN",
    "as-IN",
    "ur-IN",
    "ne-IN",
    "kok-IN",
    "ks-IN",
    "sd-IN",
    "sa-IN",
    "sat-IN",
    "mni-IN",
    "brx-IN",
    "mai-IN",
    "doi-IN",
}


async def convert_audio_to_text(
    audio_file,
    *,
    settings,
    client,
    language="unknown",
    filename="speech.webm",
    content_type="audio/webm",
):
    """Transcribe validated audio bytes with Sarvam; never fabricate a transcript."""
    if not settings.sarvam_api_key:
        raise ServiceError("Sarvam", "Set SARVAM_API_KEY in backend/.env to transcribe audio.", 503)
    if language not in LANGUAGES:
        raise ServiceError("Sarvam", "Unsupported speech language.", 422)
    result = await post_json(
        client,
        "Sarvam",
        "https://api.sarvam.ai/speech-to-text",
        headers={"api-subscription-key": settings.sarvam_api_key},
        data={"model": settings.sarvam_model, "mode": "transcribe", "language_code": language},
        files={"file": (filename, audio_file, content_type)},
    )
    transcript = result.get("transcript")
    if not isinstance(transcript, str) or not transcript.strip():
        raise ServiceError(
            "Sarvam", "No intelligible speech was returned. Try a clearer recording.", 422
        )
    if len(transcript) > 16000:
        raise ServiceError("Sarvam", "Transcript exceeds the intake text limit.", 422)
    return {
        "text": transcript.strip(),
        "language_code": result.get("language_code"),
        "provider": "sarvam",
    }
