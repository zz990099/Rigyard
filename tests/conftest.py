from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _no_terminal_colour(monkeypatch):
    """Keep captured output free of ANSI sequences; the style tests opt out."""

    monkeypatch.setenv("NO_COLOR", "1")
