import struct

import pytest
from PySide6.QtGui import QColor, QIcon, QImageReader

from perch import icons, palette
from perch.models import Group, Pin, PinKind, Shortcut

AMBER = palette.PIN_COLORS["amber"]


def entries(ico_bytes):
    """(width, height) of each image in an .ico."""
    _, kind, count = struct.unpack_from("<HHH", ico_bytes, 0)
    assert kind == 1
    sizes = []
    for i in range(count):
        w, h = struct.unpack_from("<BB", ico_bytes, 6 + 16 * i)
        sizes.append((w or 256, h or 256))
    return sizes


@pytest.mark.parametrize("size", [16, 24, 32, 256])
def test_mark_is_drawn_at_the_requested_size(qapp, size):
    image = icons.draw_mark(size, AMBER, "E")
    assert (image.width(), image.height()) == (size, size)
    # Corners stay transparent; the panel's middle is the fill colour or the letter.
    assert image.pixelColor(0, 0).alpha() == 0
    assert image.pixelColor(size // 2, size // 5).alpha() == 255


def test_mark_uses_the_group_colour(qapp):
    blue = palette.PIN_COLORS["blue"]
    image = icons.draw_mark(64, blue)
    assert image.pixelColor(40, 40) == QColor(blue.fill)  # inside the panel, right of the short row


def test_ico_holds_every_size(qapp, tmp_path):
    path = tmp_path / "pin.ico"
    group = Group("Essentials", (Shortcut("A", "a.exe"),))
    icons.write_ico(icons.pin_images(group), path)
    assert entries(path.read_bytes()) == [(s, s) for s in icons.ICO_SIZES]
    reader = QImageReader(str(path))
    assert reader.imageCount() == len(icons.ICO_SIZES)


def test_collage_is_used_when_asked(qapp):
    group = Group("G", (Shortcut("A", "a.exe"),), pin=Pin(kind=PinKind.COLLAGE))
    red = icons.monogram_icon("A")
    images = icons.pin_images(group, [red])
    # The collage's dark tile, not the amber mark.
    assert images[-1].pixelColor(128, 20) == QColor("#2B2B2B")


def test_missing_pin_file_falls_back_to_the_mark(qapp, tmp_path):
    group = Group("G", (Shortcut("A", "a.exe"),), pin=Pin(kind=PinKind.FILE, file=str(tmp_path / "gone.png")))
    image = icons.pin_images(group)[-1]  # 256 px: four pixels per design unit
    assert image.pixelColor(160, 160) == QColor(AMBER.fill)


def test_ico_pin_file_is_used_as_is(qapp, tmp_path):
    own = tmp_path / "own.ico"
    icons.write_ico([icons.draw_mark(32, AMBER)], own)
    group = Group("G", (Shortcut("A", "a.exe"),), pin=Pin(kind=PinKind.FILE, file=str(own)))
    assert icons.write_pin_icon(group, tmp_path / "out.ico") == own
    assert not (tmp_path / "out.ico").exists()


def test_targets_without_a_file_get_a_letter_tile(qapp):
    icon = icons.shortcut_icon(Shortcut("Display", "ms-settings:display"))
    assert not icon.isNull()
    assert icon.availableSizes()  # the generated monogram, not a theme icon


def test_shortcut_icon_file_wins_over_the_target(qapp, tmp_path):
    own = tmp_path / "own.png"
    icons.draw_mark(32, AMBER).save(str(own))
    icon = icons.shortcut_icon(Shortcut("A", "ms-settings:display", icon=str(own)))
    assert icon.pixmap(32, 32).toImage().pixelColor(16, 6) == QColor(AMBER.fill)


@pytest.mark.parametrize(
    ("source", "is_file"),
    [
        ("https://example.com", False),
        ("ms-settings:display", False),
        ("notepad.exe", True),
        (r"%WINDIR%\explorer.exe", True),
        (r"C:\definitely\missing.exe", False),
    ],
)
def test_resolve_path(source, is_file):
    assert (icons.resolve_path(source) is not None) is is_file


def test_app_icon_has_every_size(qapp):
    icon = icons.app_icon()
    assert isinstance(icon, QIcon)
    assert {s.width() for s in icon.availableSizes()} == set(icons.ICO_SIZES)
