"""User presets and settings, stored as JSON in the config directory."""

import json
import os
import re
import tempfile
import unicodedata
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, fields, replace
from pathlib import Path
from typing import Any

from .naming import CLASH_RULES
from .presets import BUILTIN_BY_ID, BUILTINS, Preset

BACKUP_NOTICE = ("Your presets file was unreadable and has been backed up to "
                 "presets.json.bak.")


@dataclass
class Settings:
    parallel: int | None = None
    output_dir: str | None = None
    pattern: str = "{name}"
    clash: str = "rename"
    trash_originals: bool = False

    def workers(self) -> int:
        return self.parallel or max(1, (os.cpu_count() or 2) // 2)

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "Settings":
        known = {f.name for f in fields(cls)}
        s = cls(**{k: v for k, v in d.items() if k in known})
        if s.clash not in CLASH_RULES or not isinstance(s.pattern, str):
            raise ValueError("Invalid settings")
        return s


@dataclass
class Store:
    user_presets: list[Preset] = field(default_factory=list)
    hidden_builtins: set[str] = field(default_factory=set)
    settings: Settings = field(default_factory=Settings)
    notice: str | None = None

    def all_presets(self) -> list[Preset]:
        builtins = [replace(p, in_menu=p.id not in self.hidden_builtins) for p in BUILTINS]
        return builtins + self.user_presets

    def get(self, preset_id: str) -> Preset:
        for p in self.all_presets():
            if p.id == preset_id:
                return p
        raise KeyError(preset_id)

    def add_user_preset(self, name: str, base: Preset, options: Mapping[str, Any]) -> Preset:
        taken = {p.id for p in self.user_presets}
        slug = _slug(name)
        pid, n = f"user:{slug}", 2
        while pid in taken:
            pid, n = f"user:{slug}-{n}", n + 1
        preset = Preset(pid, name.strip(), base.category, base.format, base.inputs,
                        dict(options))
        self.user_presets.append(preset)
        return preset

    def remove_user_preset(self, preset_id: str) -> None:
        self.user_presets = [p for p in self.user_presets if p.id != preset_id]

    def is_customized(self) -> bool:
        return bool(self.user_presets or self.hidden_builtins)


def _slug(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-") or "preset"


def config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "dolphin-file-converter" / "presets.json"


def lo_profile_path() -> Path:
    """LibreOffice profile kept apart from the user's own, so conversions
    work while LibreOffice is open."""
    base = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
    return Path(base) / "dolphin-file-converter" / "lo-profile"


def load(path: Path | None = None) -> Store:
    path = path or config_path()
    try:
        text = path.read_text()
    except FileNotFoundError:
        return Store()
    try:
        data = json.loads(text)
        return Store(
            user_presets=[Preset.from_dict(d) for d in data.get("presets", [])],
            hidden_builtins={i for i in data.get("hidden_builtins", []) if i in BUILTIN_BY_ID},
            settings=Settings.from_dict(data.get("settings", {})),
        )
    except (ValueError, KeyError, TypeError, AttributeError):
        os.replace(path, path.with_name(path.name + ".bak"))
        return Store(notice=BACKUP_NOTICE)


def save(st: Store, path: Path | None = None) -> None:
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "version": 1,
        "presets": [p.to_dict() for p in st.user_presets],
        "hidden_builtins": sorted(st.hidden_builtins),
        "settings": asdict(st.settings),
    }
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".presets-", suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)
