import os

import pytest

from perch import launcher
from perch.launcher import LaunchError
from perch.models import Shortcut


def test_opens_target_with_variables_expanded(monkeypatch):
    opened = []
    monkeypatch.setattr(os, "startfile", opened.append)
    monkeypatch.setenv("PERCH_TEST_DIR", r"C:\Somewhere")
    launcher.launch(Shortcut("Docs", r"%PERCH_TEST_DIR%\notes.txt"))
    assert opened == [r"C:\Somewhere\notes.txt"]


def test_failure_names_the_shortcut_and_the_reason(monkeypatch):
    def missing(path):
        raise FileNotFoundError(2, "The system cannot find the file specified", path)

    monkeypatch.setattr(os, "startfile", missing)
    with pytest.raises(LaunchError, match=r'"Ghost" \(nope\.exe\): The system cannot find'):
        launcher.launch(Shortcut("Ghost", "nope.exe"))
