import configparser
import subprocess
from pathlib import Path

from fileconverter.filetypes import KINDS, MIME_TYPES

ROOT = Path(__file__).resolve().parent.parent


def test_launcher_mime_types_match_code():
    entry = configparser.ConfigParser(interpolation=None)
    entry.read(ROOT / "data" / "fileconverter.desktop")
    section = entry["Desktop Entry"]
    mimes = section["MimeType"].rstrip(";").split(";")
    assert mimes == [m for kind in KINDS for m in MIME_TYPES[kind]]
    assert section["Exec"] == "fileconverter %F" and section["Icon"] == "fileconverter"


def test_icon_is_svg():
    assert (ROOT / "data" / "fileconverter.svg").read_text().lstrip().startswith("<svg")


def test_install_script():
    result = subprocess.run(["bash", str(ROOT / "tests" / "test_install.sh")],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
