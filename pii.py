"""
PII scrubber: masks emails, phone numbers, credit-card-like sequences.
Usage:
    from pii import scrub_text
    safe = scrub_text(user_input)
"""

import re

# Very permissive patterns (good enough for chat inputs)
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
# US-like phones: (123) 456-7890, 123-456-7890, +1 123 456 7890, 10+ digits with separators
PHONE_RE = re.compile(r"""
    (?:
        (?:(?:\+?\d{1,3}[\s\-.()]*)?)      # country code
        (?:\d{3}|\(\d{3}\))[\s\-.()]*      # area code
        \d{3}[\s\-.()]*\d{4}
    )
""", re.VERBOSE)
# Credit-card-ish: 13–19 digits possibly spaced/dashed
CC_RE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")

def _mask(match: re.Match, label: str) -> str:
    s = match.group(0)
    if len(s) <= 6:
        return f"[{label}]"
    return f"[{label}:{s[:2]}…{s[-2:]}]"

def scrub_text(text: str) -> str:
    if not text:
        return text
    out = EMAIL_RE.sub(lambda m: _mask(m, "email"), text)
    out = PHONE_RE.sub(lambda m: _mask(m, "phone"), out)
    out = CC_RE.sub(lambda m: _mask(m, "card"), out)
    return out

if __name__ == "__main__":
    demo = "Email me at john.doe@example.com or +1 (555) 123-4567. Card 4242 4242 4242 4242."
    print(scrub_text(demo))
