import pytest

from perch import palette


def test_named_colours_use_the_design_values():
    assert palette.pin_colors("Amber") == palette.PIN_COLORS["amber"]


def test_hex_colours_get_a_darker_stroke_and_ink():
    colors = palette.pin_colors("#40A0FF")
    assert colors.fill == "#40A0FF"
    assert _lightness(colors.ink) < _lightness(colors.stroke) < _lightness(colors.fill)


@pytest.mark.parametrize(("value", "ok"), [("amber", True), ("#12abEF", True), ("#12ab", False), ("red", False)])
def test_is_color(value, ok):
    assert palette.is_color(value) is ok


def test_unknown_colour_is_refused():
    with pytest.raises(ValueError):
        palette.pin_colors("red")


def _lightness(hex_color):
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (1, 3, 5))
    return max(r, g, b) + min(r, g, b)
