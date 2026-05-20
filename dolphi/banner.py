"""ASCII banner + small Rich helpers used by the CLI surfaces.

The banner is rendered at the top of every interactive command
(``dolphi`` and ``dolphi --check``). It exists for one reason: brand
recall. People who see this for ten seconds at a time, week after
week, remember it.

Rendering is via Rich so the colour respects the user's terminal
capability (auto-degrades to monochrome on pipes, CI, etc.).
"""

from __future__ import annotations

from rich.align import Align
from rich.console import Console
from rich.panel import Panel
from rich.text import Text


_ASCII = r"""
 ____    ____   _      ____   _   _  ___
|  _ \  / __ \ | |    |  _ \ | | | ||_ _|
| | | || |  | || |    | |_) || |_| | | |
| |_| || |__| || |___ |  __/ |  _  | | |
|____/  \____/ |_____||_|    |_| |_||___|
"""

_TAGLINE = "the multi-agent investment researcher that proves itself wrong"


def banner_renderable(*, subtitle: str | None = None) -> Panel:
    """Build the Rich-renderable banner. Subtitle line shows under the tagline."""
    art = Text(_ASCII.rstrip("\n"), style="bold bright_cyan", justify="left")
    tagline = Text(_TAGLINE, style="dim cyan", justify="center")
    body_parts: list[Text] = [art, Text(""), tagline]
    if subtitle:
        body_parts.append(Text(subtitle, style="bold bright_white", justify="center"))
    body = Text("\n").join(body_parts)
    return Panel(
        Align.center(body),
        border_style="cyan",
        padding=(0, 2),
        title=Text("🐬 dolphi", style="bold bright_cyan"),
        title_align="left",
    )


def print_banner(console: Console | None = None, *, subtitle: str | None = None) -> None:
    """Print the banner to ``console`` (or a freshly-built stderr console)."""
    target = console or Console()
    target.print(banner_renderable(subtitle=subtitle))
