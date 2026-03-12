import re

from django import template
from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe

register = template.Library()

_TAG_RE = re.compile(r"(<[^>]+>)")
_SUBSCRIPT_MAP = {
    "\u2080": "0",
    "\u2081": "1",
    "\u2082": "2",
    "\u2083": "3",
    "\u2084": "4",
    "\u2085": "5",
    "\u2086": "6",
    "\u2087": "7",
    "\u2088": "8",
    "\u2089": "9",
    "\u208a": "+",
    "\u208b": "-",
    "\u208c": "=",
    "\u208d": "(",
    "\u208e": ")",
}
_SUPERSCRIPT_MAP = {
    "\u2070": "0",
    "\u00b9": "1",
    "\u00b2": "2",
    "\u00b3": "3",
    "\u2074": "4",
    "\u2075": "5",
    "\u2076": "6",
    "\u2077": "7",
    "\u2078": "8",
    "\u2079": "9",
    "\u207a": "+",
    "\u207b": "-",
    "\u207c": "=",
    "\u207d": "(",
    "\u207e": ")",
    "\u207f": "n",
}


def _flush_mapped_run(parts, run, tag_name):
    if not run:
        return
    parts.append(f"<{tag_name}>{''.join(run)}</{tag_name}>")
    run.clear()


def _format_notation_segment(value):
    parts = []
    subscript_run = []
    superscript_run = []
    for char in value:
        if char in _SUBSCRIPT_MAP:
            _flush_mapped_run(parts, superscript_run, "sup")
            subscript_run.append(_SUBSCRIPT_MAP[char])
            continue
        if char in _SUPERSCRIPT_MAP:
            _flush_mapped_run(parts, subscript_run, "sub")
            superscript_run.append(_SUPERSCRIPT_MAP[char])
            continue
        _flush_mapped_run(parts, subscript_run, "sub")
        _flush_mapped_run(parts, superscript_run, "sup")
        parts.append(char)
    _flush_mapped_run(parts, subscript_run, "sub")
    _flush_mapped_run(parts, superscript_run, "sup")
    return "".join(parts)


@register.filter(needs_autoescape=True)
def cbt_notation(value, autoescape=True):
    if value in (None, ""):
        return ""
    rendered = conditional_escape(value) if autoescape else value
    parts = _TAG_RE.split(str(rendered))
    formatted = []
    for part in parts:
        if part.startswith("<") and part.endswith(">"):
            formatted.append(part)
            continue
        formatted.append(_format_notation_segment(part))
    return mark_safe("".join(formatted))
