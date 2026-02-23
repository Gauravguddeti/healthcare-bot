"""
sarvam_client.py — Sarvam AI integration for multilingual translation.
Supports translating user messages (any Indian language → English) and
bot responses (English → user's selected language).
Handles chunked translation for long texts (Sarvam has ~900 char limit per call).
"""

import os
import requests

SARVAM_API_KEY = os.environ.get("SARVAM_API_KEY", "")
TRANSLATE_URL = "https://api.sarvam.ai/translate"
MAX_CHUNK_LEN = 800  # Safe limit below Sarvam's ~1000 char cap

# Sarvam uses BCP-47-style codes: xx-IN
LANGUAGES = {
    "en-IN": "English",
    "hi-IN": "Hindi",
    "kn-IN": "Kannada",
    "ta-IN": "Tamil",
    "te-IN": "Telugu",
    "bn-IN": "Bengali",
    "mr-IN": "Marathi",
    "gu-IN": "Gujarati",
    "ml-IN": "Malayalam",
    "pa-IN": "Punjabi",
    "od-IN": "Odia",
    "ur-IN": "Urdu",
}


def _translate_chunk(text: str, source_lang: str, target_lang: str) -> str:
    """Translate a single chunk (must be under MAX_CHUNK_LEN)."""
    try:
        response = requests.post(
            TRANSLATE_URL,
            headers={
                "Content-Type": "application/json",
                "api-subscription-key": SARVAM_API_KEY,
            },
            json={
                "input": text,
                "source_language_code": source_lang,
                "target_language_code": target_lang,
                "model": "mayura:v1",
                "enable_preprocessing": True,
            },
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("translated_text", text)
    except Exception as e:
        print(f"[Sarvam] Chunk translation error: {e}")
        return text


def _split_into_chunks(text: str) -> list[str]:
    """Split text into chunks respecting paragraph and sentence boundaries."""
    # First try splitting by double newlines (paragraphs)
    paragraphs = text.split("\n\n")
    chunks = []
    current_chunk = ""

    for para in paragraphs:
        # If adding this paragraph exceeds limit, flush current chunk
        if len(current_chunk) + len(para) + 2 > MAX_CHUNK_LEN:
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = ""

            # If single paragraph is too long, split by sentences
            if len(para) > MAX_CHUNK_LEN:
                sentences = para.replace(". ", ".\n").split("\n")
                for sentence in sentences:
                    if len(current_chunk) + len(sentence) + 1 > MAX_CHUNK_LEN:
                        if current_chunk:
                            chunks.append(current_chunk.strip())
                        current_chunk = sentence
                    else:
                        current_chunk += (" " if current_chunk else "") + sentence
            else:
                current_chunk = para
        else:
            current_chunk += ("\n\n" if current_chunk else "") + para

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks if chunks else [text[:MAX_CHUNK_LEN]]


def translate(text: str, source_lang: str, target_lang: str) -> str:
    """
    Translate text between languages using Sarvam AI.
    Automatically chunks long text. Returns translated text or original on failure.
    """
    if source_lang == target_lang or not text.strip():
        return text

    # Short text — single call
    if len(text) <= MAX_CHUNK_LEN:
        return _translate_chunk(text, source_lang, target_lang)

    # Long text — chunk and translate each piece
    chunks = _split_into_chunks(text)
    translated_chunks = []
    for chunk in chunks:
        translated = _translate_chunk(chunk, source_lang, target_lang)
        translated_chunks.append(translated)

    return "\n\n".join(translated_chunks)


def translate_to_english(text: str, source_lang: str) -> str:
    """Translate user input from their language to English."""
    return translate(text, source_lang, "en-IN")


def translate_from_english(text: str, target_lang: str) -> str:
    """Translate bot response from English to user's language."""
    return translate(text, "en-IN", target_lang)


def get_supported_languages() -> dict:
    """Return mapping of language codes to names."""
    return LANGUAGES
