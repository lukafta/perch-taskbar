"""Where each tile goes. Pure functions, no Qt."""

from __future__ import annotations

import math

from perch.models import Layout


def grid_shape(count: int, layout: Layout, columns: int = 4, max_columns: int | None = None) -> tuple[int, int]:
    """``(rows, columns)`` for ``count`` tiles.

    ``max_columns`` is how many tiles fit across the screen. A layout wider
    than that wraps onto more rows rather than running off the edge.
    """
    if count <= 0:
        return (0, 0)
    match layout:
        case Layout.VERTICAL:
            cols = 1
        case Layout.HORIZONTAL:
            cols = count
        case Layout.SQUARE:
            cols = math.ceil(math.sqrt(count))
        case Layout.GRID:
            cols = min(columns, count)
    if max_columns is not None:
        cols = max(1, min(cols, max_columns))
    return (math.ceil(count / cols), cols)


def cell(index: int, columns: int) -> tuple[int, int]:
    """``(row, column)`` of tile ``index``, filling rows left to right."""
    return divmod(index, columns)
