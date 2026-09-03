import sys


def safe(text):
    encoding = getattr(sys.stdout, 'encoding', None) or 'utf-8'
    try:
        text.encode(encoding)
        return text
    except (UnicodeEncodeError, LookupError):
        return text.encode(encoding, errors='replace').decode(encoding, errors='replace')
