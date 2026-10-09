import re

_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_HEADER = re.compile(r"^#{1,6}[ \t]+", re.MULTILINE)
_LIST_MARKER = re.compile(r"^[ \t]*[-*+][ \t]+", re.MULTILINE)
_BOLD_ITALIC = re.compile(r"\*\*\*(.+?)\*\*\*|___(.+?)___")
_BOLD = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
_ITALIC = re.compile(r"\*(.+?)\*|_(.+?)_")
_STRIKETHROUGH = re.compile(r"~~(.+?)~~")
_INLINE_CODE = re.compile(r"`([^`]+?)`")
_LEFTOVER_SYMBOLS = re.compile(r"[*_`~#]")
_REPEATED_SPACES = re.compile(r"[ \t]{2,}")


def strip_markdown(text: str) -> str:
    """Strip markdown formatting so TTS doesn't vocalize symbols like * or _."""
    if not text:
        return text

    text = _IMAGE.sub(r"\1", text)
    text = _LINK.sub(r"\1", text)
    text = _HEADER.sub("", text)
    text = _LIST_MARKER.sub("", text)
    text = _BOLD_ITALIC.sub(lambda m: m.group(1) or m.group(2), text)
    text = _BOLD.sub(lambda m: m.group(1) or m.group(2), text)
    text = _ITALIC.sub(lambda m: m.group(1) or m.group(2), text)
    text = _STRIKETHROUGH.sub(r"\1", text)
    text = _INLINE_CODE.sub(r"\1", text)
    text = _LEFTOVER_SYMBOLS.sub("", text)
    text = _REPEATED_SPACES.sub(" ", text)

    return text
