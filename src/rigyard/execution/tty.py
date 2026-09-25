"""Terminal allocation policy for container-backed commands."""

from typing import Literal

TtyMode = Literal["auto", "always", "never"]
