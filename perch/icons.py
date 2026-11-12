"""Drawing Perch's icons: the app mark, group pins, and shortcut icons.

Marks are drawn with QPainter in a 64-unit square scaled to the output size,
so one description serves 16 px taskbar icons and 256 px Explorer tiles. At
24 px and below a simplified mark is drawn (bigger shapes, fewer details), the
design's small-size variant.
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import struct
from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QFileInfo, QIODevice, QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QPainter, QPainterPath, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QFileIconProvider

from perch import palette
from perch.models import Group, PinKind, Shortcut

log = logging.getLogger(__name__)

ICO_SIZES = (16, 20, 24, 32, 40, 48, 64, 256)
SMALL = 24
"""At or below this many pixels, draw the simplified mark."""
IMAGE_SUFFIXES = {".ico", ".png", ".jpg", ".jpeg", ".bmp", ".svg"}
MONOGRAM_COLORS = ("#2F5E8C", "#4A4A8C", "#8C6A1F", "#8C3F5E", "#2F7A6B", "#555D6B", "#3F6B3F", "#6B4A8C")


# -- the Perch mark --------------------------------------------------------


def draw_mark(size: int, colors: palette.PinColors, letter: str = "") -> QImage:
    """The Perch mark: a small panel perched on a ledge.

    Group pins carry ``letter`` on the panel; the app icon (no letter) shows
    the panel's rows instead.
    """
    image, painter = _canvas(size)
    small = size <= SMALL
    if small:
        panel = QRectF(10, 4, 44, 40)
        radius, tip, ledge = 10, (26, 43, 32, 50.5, 38), QRectF(6, 53, 52, 7)
    else:
        panel = QRectF(12, 6, 40, 38)
        radius, tip, ledge = 9, (27, 43, 32, 50, 37), QRectF(8, 53, 48, 5)

    body = QPainterPath()
    body.addRoundedRect(panel, radius, radius)
    pointer = QPainterPath()
    pointer.addPolygon(QPolygonF([QPointF(tip[0], tip[1]), QPointF(tip[2], tip[3]), QPointF(tip[4], tip[1])]))
    body = body.united(pointer)  # one outline, so the stroke doesn't cross the joint

    pen = QPen(QColor(colors.stroke), 2.5 if small else 2)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(QColor(colors.fill))
    painter.drawPath(body)

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(colors.ledge))
    painter.drawRoundedRect(ledge, ledge.height() / 2, ledge.height() / 2)

    ink = QColor(colors.ink)
    if letter:
        font = QFont("Segoe UI")
        font.setWeight(QFont.Weight.Bold)
        if len(letter) == 1:
            font.setPixelSize(30 if small else 24)
        else:
            font.setPixelSize(20 if small else 17)
        painter.setFont(font)
        painter.setPen(ink)
        painter.drawText(panel, Qt.AlignmentFlag.AlignCenter, letter)
    else:
        painter.setBrush(ink)
        rows = (
            [QRectF(18, 13, 28, 8), QRectF(18, 26, 20, 8)]
            if small
            else [QRectF(19, 14, 26, 5), QRectF(19, 22.5, 26, 5), QRectF(19, 31, 17, 5)]
        )
        for row in rows:
            painter.drawRoundedRect(row, row.height() / 2, row.height() / 2)
    painter.end()
    return image


def app_icon() -> QIcon:
    """Perch's own icon, at every size Windows asks for."""
    amber = palette.PIN_COLORS["amber"]
    return _icon_from(lambda size: draw_mark(size, amber), ICO_SIZES)


def gear_icon(color: str) -> QIcon:
    """A solid gear with a hole, for the panel's settings button."""

    def draw(size: int) -> QImage:
        image, painter = _canvas(size)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))
        painter.translate(32, 32)
        for _ in range(8):  # teeth, overlapping the body so they join it
            painter.drawRoundedRect(QRectF(-5.5, -29, 11, 14), 2.5, 2.5)
            painter.rotate(45)
        painter.drawEllipse(QPointF(0, 0), 21, 21)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        painter.drawEllipse(QPointF(0, 0), 8.5, 8.5)
        painter.end()
        return image

    return _icon_from(draw, (16, 20, 24, 32, 48))


# -- group pins ------------------------------------------------------------


def draw_collage(size: int, icons: Sequence[QIcon]) -> QImage:
    """A dark tile holding the first four app icons, with an amber corner dot."""
    image, painter = _canvas(size)
    painter.setPen(QPen(QColor("#4A4A4A"), 2))
    painter.setBrush(QColor("#2B2B2B"))
    painter.drawRoundedRect(QRectF(4, 4, 56, 56), 14, 14)
    pixels = max(1, round(18 * size / 64))
    for icon, (x, y) in zip(icons[:4], ((12, 12), (34, 12), (12, 34), (34, 34))):
        pixmap = icon.pixmap(QSize(pixels, pixels), 1.0)
        painter.drawPixmap(QRectF(x, y, 18, 18), pixmap, QRectF(pixmap.rect()))
    painter.setPen(QPen(QColor("#1C1C1C"), 2))
    painter.setBrush(QColor(palette.AMBER))
    painter.drawEllipse(QPointF(54, 54), 7, 7)
    painter.end()
    return image


def pin_images(group: Group, shortcut_icons: Sequence[QIcon] = ()) -> list[QImage]:
    """The group's pin at every .ico size, falling back to the tinted mark when
    the chosen collage or file can't be drawn."""
    if group.pin.kind is PinKind.COLLAGE and shortcut_icons:
        return [draw_collage(size, shortcut_icons) for size in ICO_SIZES]
    if group.pin.kind is PinKind.FILE and group.pin.file:
        chosen = _load_image(group.pin.file)
        if chosen is not None:
            return [_fit(chosen, size) for size in ICO_SIZES]
        log.warning("Pin image %s couldn't be read; using the Perch mark", group.pin.file)
    colors = palette.pin_colors(group.pin.color)
    return [draw_mark(size, colors, group.pin_letter) for size in ICO_SIZES]


def pin_icon(group: Group, shortcut_icons: Sequence[QIcon] = ()) -> QIcon:
    """The group's pin as a QIcon, for lists and previews."""
    icon = QIcon()
    for image in pin_images(group, shortcut_icons):
        icon.addPixmap(QPixmap.fromImage(image))
    return icon


def write_pin_icon(group: Group, path: Path, shortcut_icons: Sequence[QIcon] = ()) -> Path:
    """Write the group's pin to ``path`` as an .ico and return the icon file to use.

    A pin that already is an .ico file is used as it is, not copied.
    """
    if group.pin.kind is PinKind.FILE and group.pin.file:
        chosen = resolve_path(group.pin.file)
        if chosen is not None and chosen.suffix.lower() == ".ico":
            return chosen
    write_ico(pin_images(group, shortcut_icons), path)
    return path


def write_ico(images: Sequence[QImage], path: Path) -> None:
    """Pack square images into one .ico, each entry PNG-compressed (Windows Vista and later)."""
    blobs = [_png_bytes(image) for image in images]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries = b""
    for image, blob in zip(images, blobs):
        # Width and height are stored in one byte each, where 0 means 256.
        entries += struct.pack("<BBBBHHII", image.width() % 256, image.height() % 256, 0, 0, 1, 32, len(blob), offset)
        offset += len(blob)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + entries + b"".join(blobs))


# -- shortcut icons --------------------------------------------------------


def shortcut_icon(shortcut: Shortcut, provider: QFileIconProvider | None = None) -> QIcon:
    """The icon to show for a shortcut.

    Tries the shortcut's own ``icon``, then the icon Windows shows for its
    target, then falls back to a coloured tile with the name's first letter
    (URLs and ``ms-settings:`` pages have no file to take an icon from).
    """
    for source in (shortcut.icon, shortcut.target):
        if not source:
            continue
        path = resolve_path(source)
        if path is None:
            continue
        if path.suffix.lower() in IMAGE_SUFFIXES:
            icon = QIcon(str(path))
        else:
            icon = (provider or QFileIconProvider()).icon(QFileInfo(str(path)))
        if not icon.isNull():
            return icon
    return monogram_icon(shortcut.name)


def monogram_icon(name: str) -> QIcon:
    """A rounded tile with the name's first letter, in a colour picked from the name."""
    digest = int(hashlib.sha1(name.encode("utf-8")).hexdigest(), 16)
    color = QColor(MONOGRAM_COLORS[digest % len(MONOGRAM_COLORS)])
    letter = next((c.upper() for c in name if c.isalnum()), "?")

    def draw(size: int) -> QImage:
        image, painter = _canvas(size)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawRoundedRect(QRectF(2, 2, 60, 60), 14, 14)
        font = QFont("Segoe UI")
        font.setWeight(QFont.Weight.DemiBold)
        font.setPixelSize(34)
        painter.setFont(font)
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(QRectF(2, 2, 60, 60), Qt.AlignmentFlag.AlignCenter, letter)
        painter.end()
        return image

    return _icon_from(draw, (16, 20, 24, 32, 40, 48, 64))


def resolve_path(source: str) -> Path | None:
    """The existing file ``source`` names, or None.

    Expands ``%VARIABLES%`` and ``~``, and looks bare program names like
    ``notepad.exe`` up on PATH. URLs and other ``scheme:`` targets aren't files.
    """
    expanded = os.path.expanduser(os.path.expandvars(source))
    scheme, colon, _ = expanded.partition(":")
    if colon and len(scheme) > 1:  # "C:" is a drive, "https:" is a scheme
        return None
    path = Path(expanded)
    if path.is_absolute():
        return path if path.exists() else None
    found = shutil.which(expanded)
    return Path(found) if found else None


# -- helpers ---------------------------------------------------------------


def _canvas(size: int) -> tuple[QImage, QPainter]:
    """A transparent square image with a painter whose coordinates run 0-64."""
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHints(
        QPainter.RenderHint.Antialiasing
        | QPainter.RenderHint.TextAntialiasing
        | QPainter.RenderHint.SmoothPixmapTransform
    )
    painter.scale(size / 64, size / 64)
    return image, painter


def _icon_from(draw, sizes: Sequence[int]) -> QIcon:
    icon = QIcon()
    for size in sizes:
        icon.addPixmap(QPixmap.fromImage(draw(size)))
    return icon


def _load_image(source: str) -> QImage | None:
    path = resolve_path(source)
    if path is None:
        return None
    image = QImage(str(path))
    return None if image.isNull() else image


def _fit(image: QImage, size: int) -> QImage:
    """``image`` scaled to fit a transparent ``size`` square, centred."""
    scaled = image.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    canvas = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    painter.drawImage((size - scaled.width()) // 2, (size - scaled.height()) // 2, scaled)
    painter.end()
    return canvas


def _png_bytes(image: QImage) -> bytes:
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    buffer.close()
    return bytes(data)
