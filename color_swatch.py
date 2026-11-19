"""Recognize clipboard entries that consist only of a hex color."""

import re


def rgba(value):
    match = re.fullmatch(r"#([0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})", value.strip())
    if not match:
        return None
    digits = match.group(1)
    if len(digits) in (3, 4):
        digits = "".join(char * 2 for char in digits)
    if len(digits) == 6:
        digits += "ff"
    return int(digits, 16)
