import httpx


class ServiceError(Exception):
    def __init__(self, provider, message, status=502):
        self.provider, self.message, self.status = provider, message, status
        super().__init__(message)


async def post_json(client, provider, url, **kwargs):
    try:
        response = await client.post(url, **kwargs)
        if response.status_code in (401, 403):
            raise ServiceError(
                provider,
                f"{provider} rejected its API key or account permissions. Check backend configuration.",
                503,
            )
        if response.status_code == 429:
            raise ServiceError(
                provider, f"{provider} quota or rate limit reached. Retry later.", 503
            )
        if provider == "Gemini" and response.status_code == 404:
            raise ServiceError(
                provider,
                "The configured Gemini model is unavailable for this API key (HTTP 404). "
                "Set GEMINI_MODEL in backend/.env to an accessible model such as "
                "gemini-3.5-flash, then restart the app. Your intake is saved; retry Review summary.",
                503,
            )
        if response.status_code >= 400:
            raise ServiceError(
                provider,
                f"{provider} could not process this request (HTTP {response.status_code}). Check the file, model, and account configuration.",
            )
        if len(response.content) > 2 * 1024 * 1024:
            raise ServiceError(provider, f"{provider} returned an unexpectedly large response.")
        result = response.json()
        if not isinstance(result, dict):
            raise ValueError("Expected JSON object")
        return result
    except httpx.RequestError:
        raise ServiceError(
            provider,
            f"{provider} is temporarily unreachable. Retry without losing the saved intake.",
            503,
        ) from None
    except (ValueError, TypeError):
        raise ServiceError(provider, f"{provider} returned an invalid response.") from None
