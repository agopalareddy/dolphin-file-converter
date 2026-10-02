"""Output file names: pattern rendering and what to do when a name is taken."""

from datetime import date
from pathlib import Path
from string import Formatter

CLASH_RULES = ("rename", "overwrite", "skip")
TOKENS = ("name", "preset", "date")


def render(pattern: str, *, name: str, preset_name: str, today: date) -> str:
    """Fill ``{name}``, ``{preset}`` and ``{date}`` into ``pattern``.

    Raises ValueError for unknown tokens, format specs, unbalanced braces
    or an empty result.
    """
    try:
        parts = list(Formatter().parse(pattern))
    except ValueError as e:
        raise ValueError(f"Invalid name pattern: {e}") from None
    values = {"name": name, "preset": preset_name, "date": today.isoformat()}
    out = []
    for literal, field, spec, conv in parts:
        out.append(literal)
        if field is None:
            continue
        if field not in values or spec or conv:
            raise ValueError(f"Unknown name token: {{{field}}}")
        out.append(values[field])
    result = "".join(out).replace("/", "_").replace("\0", "_").strip()
    if not result:
        raise ValueError("Name pattern gives an empty file name")
    return result


def resolve(folder: Path, stem: str, ext: str, clash: str) -> Path | None:
    """Pick the output path for ``stem.ext`` in ``folder``; None means skip."""
    path = folder / f"{stem}.{ext}"
    if clash == "overwrite" or not path.exists():
        return path
    if clash == "skip":
        return None
    n = 1
    while (path := folder / f"{stem} ({n}).{ext}").exists():
        n += 1
    return path
