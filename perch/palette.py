"""Brand and pin colours. Plain data, shared by config validation and drawing."""

from __future__ import annotations

import colorsys
import re
from dataclasses import dataclass

AMBER = "#FFB547"
"""The brand accent: the app icon, focus rings, selection."""


@dataclass(frozen=True)
class PinColors:
    """The four colours a tinted Perch mark is drawn with."""

    fill: str
    stroke: str
    ledge: str
    ink: str
    """Letter (or rows) drawn on the fill."""


# Hand-tuned sets from the design; any other #RRGGBB is derived by pin_colors().
PIN_COLORS = {
    "amber": PinColors(AMBER, "#D17A00", "#E8890C", "#4A3208"),
    "blue": PinColors("#7CCBFF", "#2F8FCC", "#2F8FCC", "#0B3550"),
    "violet": PinColors("#C9B0FF", "#8E66E8", "#8E66E8", "#2E1A5C"),
    "green": PinColors("#8EE3A4", "#3FA35A", "#3FA35A", "#123D1E"),
    "pink": PinColors("#FFA3C4", "#D9578A", "#D9578A", "#5C1530"),
}

_HEX = re.compile(r"#[0-9A-Fa-f]{6}")


def is_color(value: str) -> bool:
    """A colour name from PIN_COLORS or a #RRGGBB hex value."""
    return value.lower() in PIN_COLORS or _HEX.fullmatch(value) is not None


def pin_colors(value: str) -> PinColors:
    """The colour set for ``value``: a named set, or one derived from a hex fill."""
    named = PIN_COLORS.get(value.lower())
    if named is not None:
        return named
    if _HEX.fullmatch(value) is None:
        raise ValueError(f"not a colour: {value!r}")
    r, g, b = (int(value[i : i + 2], 16) / 255 for i in (1, 3, 5))
    hue, light, sat = colorsys.rgb_to_hls(r, g, b)
    return PinColors(
        fill=value.upper(),
        stroke=_hls(hue, light * 0.62, sat),
        ledge=_hls(hue, light * 0.70, sat),
        ink=_hls(hue, 0.16, min(sat, 0.75)),
    )


def _hls(hue: float, light: float, sat: float) -> str:
    r, g, b = colorsys.hls_to_rgb(hue, light, sat)
    return "#{:02X}{:02X}{:02X}".format(*(round(c * 255) for c in (r, g, b)))
