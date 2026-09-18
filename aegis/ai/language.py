"""Deterministic response-language selection for operator interactions.

This module intentionally has no model or network dependency. The latest
operator message is the source of truth, and an explicit language request
always wins over script-based detection.
"""

from __future__ import annotations

import re
import unicodedata
from enum import Enum


class ResponseLanguage(str, Enum):
    ARABIC = "Arabic"
    ENGLISH = "English"
    TURKISH = "Turkish"

    @property
    def locale(self) -> str:
        return {
            ResponseLanguage.ARABIC: "ar",
            ResponseLanguage.ENGLISH: "en",
            ResponseLanguage.TURKISH: "tr",
        }[self]


# Arabic supplements and presentation forms are included because copied text
# and browser transcriptions can use more than the basic Arabic block.
_ARABIC_LETTERS = re.compile(r"[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff\ufb50-\ufdff\ufe70-\ufeff]")
# Input is case-folded before this check. Do not use IGNORECASE here: Python
# considers plain Latin "I" equivalent to the Turkish dotless "ı", which
# would misclassify ordinary English requests as Turkish.
_TURKISH_LETTERS = re.compile(r"[çğıöşü]")
_WORDS = re.compile(r"[a-zA-ZçğıöşüÇĞİÖŞÜ]+")

_TURKISH_SIGNAL_WORDS = {
    "acik", "açık", "aktif", "alarmlar", "anlat", "bak", "bana", "bir",
    "bul", "bu", "cevap", "goster", "göster", "hangi", "kamera",
    "kameralar", "kac", "kaç", "lütfen", "lutfen", "mi", "mı", "mu", "mü",
    "nedir", "olay", "risk", "sistem", "tehlike", "var", "yardim", "yardım",
}


def _normalise(text: str) -> str:
    return unicodedata.normalize("NFKC", text).casefold()


def _explicit_response_language(normalized: str) -> ResponseLanguage | None:
    """Return a deliberate response-language command, if one is present."""
    command_groups = (
        (
            ResponseLanguage.ARABIC,
            (
                r"\b(?:speak|reply|respond|answer|talk)\s+(?:in\s+)?arabic\b",
                r"\barabic\s+(?:please|only)\b",
                r"(?:تكلم|تحدث|اجب|أجب|رد)\s+(?:بال)?عربي(?:ة)?",
                r"\barapça\s+(?:konuş|konus|cevap|yanıt|yanit)\b",
            ),
        ),
        (
            ResponseLanguage.ENGLISH,
            (
                r"\b(?:speak|reply|respond|answer|talk)\s+(?:in\s+)?english\b",
                r"(?:تكلم|تحدث|اجب|أجب|رد)\s+(?:بال)?(?:انجليزي|إنجليزي|الانجليزية|الإنجليزية)",
                r"\bingilizce\s+(?:konuş|konus|cevap|yanıt|yanit)\b",
            ),
        ),
        (
            ResponseLanguage.TURKISH,
            (
                r"\b(?:speak|reply|respond|answer|talk)\s+(?:in\s+)?turkish\b",
                r"(?:تكلم|تحدث|اجب|أجب|رد)\s+(?:بال)?(?:تركي|التركية)",
                r"\btürkçe\s+(?:konuş|konus|cevap|yanıt|yanit)\b",
                r"\bturkce\s+(?:konuş|konus|cevap|yanıt|yanit)\b",
            ),
        ),
    )
    for language, patterns in command_groups:
        if any(re.search(pattern, normalized, flags=re.IGNORECASE) for pattern in patterns):
            return language
    return None


def detect_response_language(message: str) -> ResponseLanguage:
    """Choose a response language from the latest operator message.

    Arabic script takes priority for meaningful mixed Arabic-English requests,
    unless a user explicitly asks for another response language. Turkish is
    detected from distinctive characters or multiple common Turkish terms.
    Everything else safely defaults to English.
    """
    normalized = _normalise(message)
    explicit = _explicit_response_language(normalized)
    if explicit is not None:
        return explicit

    if len(_ARABIC_LETTERS.findall(normalized)) >= 2:
        return ResponseLanguage.ARABIC

    words = set(_WORDS.findall(normalized))
    if _TURKISH_LETTERS.search(normalized) or len(words & _TURKISH_SIGNAL_WORDS) >= 2:
        return ResponseLanguage.TURKISH

    return ResponseLanguage.ENGLISH


def response_language_instruction(language: ResponseLanguage) -> str:
    """Instruction inserted immediately before the provider receives a turn."""
    return (
        f"RESPONSE LANGUAGE (MANDATORY): {language.value}. "
        f"Respond only in {language.value}, unless the operator explicitly requests another language. "
        "Keep Aegis calm, firm, serious, concise, and evidence-first."
    )


def live_turn_with_language(message: str, language: ResponseLanguage) -> str:
    """Bind a Live turn to its detected language without changing raw audio."""
    return f"{response_language_instruction(language)}\n\nOperator request: {message}"


def processing_error_message(language: ResponseLanguage) -> str:
    """Safe local error text when an AI response cannot be produced."""
    return {
        ResponseLanguage.ARABIC: "تعذّرت معالجة الطلب الآن. يُرجى المحاولة مرة أخرى.",
        ResponseLanguage.TURKISH: "İstek şu anda işlenemedi. Lütfen tekrar deneyin.",
        ResponseLanguage.ENGLISH: "I couldn't process your request. Please try again.",
    }[language]
