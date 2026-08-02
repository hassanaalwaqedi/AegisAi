"""Conservative normalization and validation for common Turkish plate forms."""

from __future__ import annotations

import re

from aegis.video.vehicle_types import PlateValidation

_PLATE_PATTERN = re.compile(r"^(0[1-9]|[1-7][0-9]|8[01])([A-Z]{1,3})([0-9]{2,4})$")
_LETTER_FIXES = str.maketrans({"0": "O", "1": "I", "5": "S", "8": "B", "2": "Z"})
_DIGIT_FIXES = str.maketrans({"O": "0", "Q": "0", "I": "1", "L": "1", "S": "5", "B": "8", "Z": "2"})


def validate_turkish_plate(raw_text: str | None) -> PlateValidation:
    """Validate only a clear 01--81 + letters + digits OCR candidate.

    Corrections are position-aware and intentionally limited.  Ambiguous or
    malformed OCR is rejected instead of being presented as an identity claim.
    """
    compact = re.sub(r"[^A-Za-z0-9]", "", raw_text or "").upper()
    if len(compact) < 5:
        return PlateValidation(False, reason="invalid_format")
    province = compact[:2].translate(_DIGIT_FIXES)
    if not province.isdigit() or not 1 <= int(province) <= 81:
        return PlateValidation(False, reason="invalid_province")
    remainder = compact[2:]
    for letter_length in (1, 2, 3):
        letters = remainder[:letter_length].translate(_LETTER_FIXES)
        digits = remainder[letter_length:].translate(_DIGIT_FIXES)
        # Do not rely on the regex engine to repartition a combined string;
        # otherwise a malformed numeric segment such as ``C123`` could be
        # silently reinterpreted as an additional letter.
        if not letters.isalpha() or not digits.isdigit() or not 2 <= len(digits) <= 4:
            continue
        candidate = f"{province}{letters}{digits}"
        match = _PLATE_PATTERN.fullmatch(candidate)
        if match:
            return PlateValidation(True, f"{province} {letters} {digits}")
    return PlateValidation(False, reason="invalid_format")
