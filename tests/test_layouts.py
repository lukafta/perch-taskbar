import pytest

from perch.layouts import cell, grid_shape
from perch.models import Layout


@pytest.mark.parametrize(
    ("layout", "count", "shape"),
    [
        (Layout.VERTICAL, 4, (4, 1)),
        (Layout.HORIZONTAL, 4, (1, 4)),
        (Layout.SQUARE, 4, (2, 2)),
        (Layout.SQUARE, 5, (2, 3)),
        (Layout.SQUARE, 9, (3, 3)),
        (Layout.SQUARE, 10, (3, 4)),
        (Layout.GRID, 10, (3, 4)),
        (Layout.GRID, 2, (1, 2)),  # fewer tiles than columns: no empty columns
        (Layout.SQUARE, 1, (1, 1)),
    ],
)
def test_grid_shape(layout, count, shape):
    assert grid_shape(count, layout, columns=4) == shape


def test_empty_group_has_no_cells():
    assert grid_shape(0, Layout.GRID) == (0, 0)


def test_too_wide_wraps_to_max_columns():
    assert grid_shape(12, Layout.HORIZONTAL, max_columns=5) == (3, 5)
    assert grid_shape(12, Layout.GRID, columns=8, max_columns=5) == (3, 5)


def test_max_columns_never_drops_below_one():
    assert grid_shape(3, Layout.HORIZONTAL, max_columns=0) == (3, 1)


def test_cells_fill_rows_left_to_right():
    assert [cell(i, 3) for i in range(5)] == [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1)]
