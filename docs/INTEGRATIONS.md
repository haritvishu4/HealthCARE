# Provider contracts and extension points

Provider credentials are read from backend settings at runtime. The adapters use bounded-timeout HTTP requests, and validation errors stop the pipeline without fabricating output. Provider URLs are fixed in service code; user input cannot select an arbitrary upstream URL.

| Adapter | Contract used | Source |
| --- | --- | --- |
| `sarvam_service.py` | Multipart short-recording transcription; `api-subscription-key` header; `saaras:v3`, `mode=transcribe`, BCP-47 language or `unknown` | [Sarvam Speech-to-Text API](https://docs.sarvam.ai/api-reference/speech-to-text/transcribe) |
| `gemini_service.py` | Gemini `generateContent`, API-key header, JSON response MIME type, schema/prompt instructions, Pydantic validation | [Gemini API reference](https://ai.google.dev/api/generate-content), [structured output guidance](https://ai.google.dev/gemini-api/docs/structured-output) |
| `ocr_service.py` | OCR.space multipart image/PDF parsing with `apikey`; per-page success checks | [OCR.space API](https://ocr.space/ocrapi) |
| `security.py` | Configured project's asymmetric JWT/JWKS verification | [Supabase JWT documentation](https://supabase.com/docs/guides/auth/jwts) |

`GEMINI_MODEL` and `SARVAM_MODEL` are environment settings so they can change without redesigning the UI. The supplied defaults are `gemini-3.5-flash` and `saaras:v3`. Confirm your account's model access and quota; model lifecycles change. [Gemini 3.5 Flash](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash) is a stable model supporting structured output, checked on 14 September 2026. A live fictional-input check returned a validated draft with the configured development key. This verifies connectivity and the response contract, not clinical correctness.

Google has [limited Gemini 2.5 access based on prior use](https://discuss.ai.google.dev/t/auth-key-can-list-models-but-generatecontent-returns-http-404-not-found-for-gemini-2-5-flash/180197/2). A model can appear in `models.list` while `generateContent` returns HTTP 404 for a particular key. The adapter reports an actionable configuration error and preserves the saved intake. Update `GEMINI_MODEL` and restart the launcher; the app does not silently switch models.

The Gemini adapter requests JSON-only output with the schema in its prompt and validates it locally. Schema validity does not validate clinical correctness. To adopt another generation endpoint or enforce its native schema parameter, change this adapter and its contract tests while keeping `ClinicalReport` stable.

The OCR adapter is deliberately replaceable. It is text extraction from documents, not radiology image interpretation. OCR confidence is returned as null rather than an invented score. `OCR_LANGUAGE` defaults to `eng`; use a provider-supported value for other document languages. Sarvam speech-language coverage and OCR document-language coverage are separate capabilities.

Bundled fonts are DejaVu and Noto, with their license texts in `backend/app/fonts/`. Noto font files came from the [Noto fonts repository](https://github.com/notofonts/noto-fonts). Optional `PDF_FONT_PATH` and `PDF_BOLD_FONT_PATH` environment overrides must be set in the actual process environment before application startup; bundled Noto fonts provide fallback script coverage.
