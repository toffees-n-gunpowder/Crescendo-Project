"""
Console output helpers.

Jamendo track and artist names are full of accents, CJK and emoji. The default
Windows console codepage is cp1252, which raises UnicodeEncodeError the moment
one of those reaches stdout - so management commands route their output through
`safe()` before writing.
"""

import sys


def safe(text):
    """Return `text` with characters the console cannot render replaced by '?'."""
    encoding = getattr(sys.stdout, 'encoding', None) or 'utf-8'
    try:
        text.encode(encoding)
        return text
    except (UnicodeEncodeError, LookupError):
        return text.encode(encoding, errors='replace').decode(encoding, errors='replace')
