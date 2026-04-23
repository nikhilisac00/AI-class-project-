# tools/validation.py
"""Input validation for pipeline entry points."""

import re


# Characters allowed in firm name input
_ALLOWED_PATTERN = re.compile(r"^[a-zA-Z0-9 .,\'&()\-/]+$")


def validate_firm_input(value: str) -> str:
    """Validate and sanitize firm name or CRD input.

    Returns cleaned input string.
    Raises ValueError if input is invalid.
    """
    cleaned = value.strip()

    if not cleaned:
        raise ValueError("Firm name or CRD is required")

    if len(cleaned) > 200:
        raise ValueError("Input too long (max 200 characters)")

    # CRD validation: purely numeric input
    if cleaned.isdigit():
        if len(cleaned) > 10:
            raise ValueError(
                f"CRD number must be 1-10 digits, got {len(cleaned)}"
            )
        return cleaned

    # Firm name character validation
    if not _ALLOWED_PATTERN.match(cleaned):
        bad_chars = set(re.findall(r"[^a-zA-Z0-9 .,\'&()\-/]", cleaned))
        raise ValueError(
            f"Invalid characters in firm name: {bad_chars}"
        )

    return cleaned
