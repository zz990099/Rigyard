"""Record the real CLI in a PTY and render a short README walkthrough.

Optional recording dependencies: Pillow, pexpect, pyte. See docs/development/demo.md.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
from pathlib import Path

import pexpect
import pyte
import yaml
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
COLUMNS, ROWS = 100, 26
CELL_WIDTH, CELL_HEIGHT = 10, 21
BACKGROUND, FOREGROUND = "#0e1726", "#dbe7f3"
COLORS = {
    "black": "#182338",
    "red": "#f38b92",
    "green": "#82d9ad",
    "brown": "#ecc58c",
    "blue": "#89b9fa",
    "magenta": "#c5a2ee",
    "cyan": "#5ee0d0",
    "white": FOREGROUND,
    "default": FOREGROUND,
}


class Recording:
    def __init__(self, output: Path, font_path: str) -> None:
        self.output = output
        self.screen = pyte.Screen(COLUMNS, ROWS)
        self.stream = pyte.Stream(self.screen)
        self.font = ImageFont.truetype(font_path, 16)
        self.heading_font = ImageFont.truetype(font_path, 15)
        self.frames: list[Image.Image] = []
        self.durations: list[int] = []
        self.events: list[list[object]] = []
        self.elapsed = 0.0
        self.chapter = "01 / Explore the interactive menu"

    def write(self, data: str) -> None:
        self.events.append([round(self.elapsed, 3), "o", data])
        self.stream.feed(data)
        self.snapshot(60)

    def flush(self) -> None:
        pass

    def snapshot(self, milliseconds: int) -> None:
        canvas = Image.new("RGB", (1048, 670), BACKGROUND)
        draw = ImageDraw.Draw(canvas)
        draw.rounded_rectangle((12, 12, 1036, 658), radius=14, outline="#2b3c53", width=1)
        for x, color in ((35, "#f38b92"), (55, "#ecc58c"), (75, "#82d9ad")):
            draw.ellipse((x, 30, x + 9, 39), fill=color)
        draw.text(
            (112, 24),
            "RIGYARD / configuration-driven development",
            font=self.heading_font,
            fill="#9fb3c9",
        )
        draw.line((24, 55, 1024, 55), fill="#2b3c53")
        for row in range(ROWS):
            for column in range(COLUMNS):
                cell = self.screen.buffer[row][column]
                if cell.data == " ":
                    continue
                color = COLORS.get(cell.fg, "#" + cell.fg)
                if cell.fg == "default" and not cell.bold:
                    color = FOREGROUND
                draw.text(
                    (24 + column * CELL_WIDTH, 72 + row * CELL_HEIGHT),
                    cell.data,
                    font=self.font,
                    fill=color,
                )
        draw.line((24, 627, 1024, 627), fill="#2b3c53")
        draw.text((26, 634), self.chapter, font=self.heading_font, fill="#5ee0d0")
        self.frames.append(canvas)
        self.durations.append(milliseconds)
        self.elapsed += milliseconds / 1000

    def hold(self, milliseconds: int) -> None:
        self.durations[-1] += milliseconds
        self.elapsed += milliseconds / 1000

    def save(self) -> None:
        self.output.mkdir(parents=True, exist_ok=True)
        # One palette prevents color flicker and keeps the GIF small.
        palette = self.frames[0].quantize(colors=64)
        frames = [
            frame.quantize(palette=palette, dither=Image.Dither.NONE) for frame in self.frames
        ]
        frames[0].save(
            self.output / "terminal-demo.gif",
            save_all=True,
            append_images=frames[1:],
            duration=self.durations,
            loop=0,
            optimize=True,
        )
        header = {"version": 2, "width": COLUMNS, "height": ROWS, "title": "Rigyard walkthrough"}
        with (self.output / "terminal-demo.cast").open("w", encoding="utf-8") as file:
            for event in [header, *self.events]:
                file.write(json.dumps(event, ensure_ascii=False) + "\n")
        print(f"Recorded {len(frames)} frames / {self.elapsed:.1f}s to {self.output}")


def record(output: Path, font: str) -> None:
    if shutil.which("rigyard") is None:
        raise SystemExit("Install Rigyard before recording the demo.")
    capture = Recording(output, font)
    with tempfile.TemporaryDirectory(prefix="rigyard-demo-") as temporary:
        project = Path(temporary) / "robot-development"
        shutil.copytree(ROOT / "examples/robot-development", project)
        manifest = project / "rigyard.yaml"
        config = yaml.safe_load(manifest.read_text())
        # Show the built-in Rigyard logo, keeping all operation definitions unchanged.
        config.pop("branding", None)
        manifest.write_text(yaml.safe_dump(config, sort_keys=False))
        env = {**os.environ, "TERM": "xterm-256color", "PS1": "$ ", "PS2": "> "}
        env.pop("NO_COLOR", None)
        with pexpect.spawn(
            "bash",
            ["--noprofile", "--norc", "-i"],
            cwd=project,
            env=env,
            encoding="utf-8",
            dimensions=(ROWS, COLUMNS),
            timeout=15,
        ) as shell:
            shell.logfile_read = capture
            shell.expect_exact("$ ")

            def type_command(command: str) -> None:
                for character in command:
                    shell.send(character)
                    shell.expect_exact(character)
                capture.hold(500)
                shell.sendline()

            def finish_command() -> None:
                shell.expect_exact("$ ")
                # Check the actual exit status without adding verification commands to the GIF.
                shell.logfile_read = None
                shell.sendline("test $? -eq 0 && printf '__RIGYARD_OK__'")
                shell.expect(r"[\r\n]__RIGYARD_OK__")
                shell.expect_exact("$ ")
                shell.logfile_read = capture

            type_command("rigyard")
            shell.expect_exact("Select [0-6]: ")
            capture.hold(3000)
            type_command("4")
            shell.expect_exact("Select [0-3]: ")
            capture.hold(2500)
            type_command("0")
            finish_command()

            capture.chapter = "02 / Validate the project configuration"
            shell.sendline("clear")
            shell.expect_exact("$ ")
            type_command("rigyard validate")
            finish_command()
            capture.hold(3000)

            capture.chapter = "03 / Preview a scene -- dry run, no containers started"
            shell.sendline("clear")
            shell.expect_exact("$ ")
            type_command("rigyard scene start robot-system development --dry-run")
            shell.expect_exact("Enter the ROS domain ID")
            capture.hold(700)
            shell.sendline()
            finish_command()
            capture.hold(6000)
    capture.save()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/assets")
    parser.add_argument(
        "--font", default="DejaVuSansMono.ttf", help="Path or name of a monospace TTF"
    )
    args = parser.parse_args()
    record(args.output.resolve(), args.font)
