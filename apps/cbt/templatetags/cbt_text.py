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
_MIXED_FRACTION_RE = re.compile(r"(?<![\w>])(\d+)\s+(\d+)\/(\d+)(?![\w<])")
_FRACTION_RE = re.compile(
    r"(?<![\w>])"
    r"([A-Za-z0-9]+(?:\^[+-]?\d+)?)"
    r"\/"
    r"([A-Za-z0-9]+(?:\^[+-]?\d+)?)"
    r"(?![\w<])"
)
_COMPLEX_FRACTION_RE = re.compile(
    r"(?<![\w>])"
    r"(\([^()]+\)|[A-Za-z0-9.\-+]+(?:\^[+-]?\d+)?)"
    r"\s*\/\s*"
    r"(\([^()]+\)|[A-Za-z0-9.\-+]+(?:\^[+-]?\d+)?)"
    r"(?![\w<])"
)
_EXPONENT_RE = re.compile(r"(\([^)]+\)|[A-Za-z0-9]+)\^([+-]?\d+)")
_FRACTIONAL_EXPONENT_RE = re.compile(r"(\([^)]+\)|[A-Za-z0-9.]+)\^([+-]?\d+)\/(\d+)")
_DEGREES_RE = re.compile(r"(?<=\d|\))\s*degrees?\b", re.IGNORECASE)
_LOGIC_CARET_RE = re.compile(r"(?<=[A-Za-z0-9)\]])\s*\^\s*(?=[A-Za-z0-9(~])")


def _flush_mapped_run(parts, run, tag_name):
    if not run:
        return
    parts.append(f"<{tag_name}>{''.join(run)}</{tag_name}>")
    run.clear()


def _format_fraction_token(token):
    return _EXPONENT_RE.sub(lambda match: f"{match.group(1)}<sup>{match.group(2)}</sup>", token)


def _replace_mixed_fractions(value):
    return _MIXED_FRACTION_RE.sub(
        lambda match: (
            f"{match.group(1)} "
            f"<sup>{_format_fraction_token(match.group(2))}</sup>&frasl;<sub>{_format_fraction_token(match.group(3))}</sub>"
        ),
        value,
    )


def _replace_fractions(value):
    return _FRACTION_RE.sub(
        lambda match: (
            f"<sup>{_format_fraction_token(match.group(1))}</sup>"
            f"&frasl;"
            f"<sub>{_format_fraction_token(match.group(2))}</sub>"
        ),
        value,
    )


def _replace_complex_fractions(value):
    return _COMPLEX_FRACTION_RE.sub(
        lambda match: (
            f"<sup>{_format_fraction_token(match.group(1))}</sup>"
            f"&frasl;"
            f"<sub>{_format_fraction_token(match.group(2))}</sub>"
        ),
        value,
    )


def _replace_exponents(value):
    return _EXPONENT_RE.sub(lambda match: f"{match.group(1)}<sup>{match.group(2)}</sup>", value)


def _replace_fractional_exponents(value):
    return _FRACTIONAL_EXPONENT_RE.sub(
        lambda match: f"{match.group(1)}<sup>{match.group(2)}&frasl;{match.group(3)}</sup>",
        value,
    )


def _replace_degrees(value):
    return _DEGREES_RE.sub("&deg;", value)


def _replace_logic_carets(value):
    return _LOGIC_CARET_RE.sub(" &and; ", value)


def _format_plain_notation(value):
    value = _replace_mixed_fractions(value)
    value = _replace_fractional_exponents(value)
    value = _replace_fractions(value)
    value = _replace_complex_fractions(value)
    value = _replace_exponents(value)
    value = _replace_degrees(value)
    value = _replace_logic_carets(value)
    return value


def _format_notation_segment(value):
    value = _format_plain_notation(value)
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
