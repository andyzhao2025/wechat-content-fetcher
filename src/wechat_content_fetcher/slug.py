from __future__ import annotations

import hashlib
import re


def slugify(value: str, fallback_prefix: str = "article") -> str:
    ascii_slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if ascii_slug:
        return ascii_slug[:80]

    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]
    return f"{fallback_prefix}-{digest}"
