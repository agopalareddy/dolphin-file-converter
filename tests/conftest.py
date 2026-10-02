"""Sample media for tests, generated once per session with the real tools.

Each ``sample_*`` fixture hands a test its own copy in ``tmp_path``, so
outputs written next to it never leak between tests.
"""

import shutil
import subprocess
from pathlib import Path

import pytest


def _need(*tools: str) -> None:
    for tool in tools:
        if shutil.which(tool) is None:
            pytest.skip(f"{tool} not installed")


def _run(*argv: str, cwd: Path | None = None) -> None:
    subprocess.run(argv, cwd=cwd, check=True, capture_output=True)


def _soffice(src: Path, fmt: str, lo: Path, *extra: str) -> Path:
    _run("soffice", f"-env:UserInstallation={lo.as_uri()}", "--headless", *extra,
         "--convert-to", fmt, "--outdir", str(src.parent), str(src))
    return src.with_suffix(f".{fmt}")


@pytest.fixture(scope="session")
def masters(tmp_path_factory):
    return tmp_path_factory.mktemp("masters")


@pytest.fixture(scope="session")
def lo_profile(tmp_path_factory):
    return tmp_path_factory.mktemp("lo") / "profile"


@pytest.fixture(scope="session")
def _wav(masters):
    _need("ffmpeg")
    out = masters / "tone.wav"
    _run("ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "sine=duration=2", str(out))
    return out


@pytest.fixture(scope="session")
def _mp4(masters):
    _need("ffmpeg")
    out = masters / "clip.mp4"
    _run("ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i",
         "testsrc=size=321x241:rate=25:duration=2", "-f", "lavfi", "-i", "sine=duration=2",
         "-c:v", "libx264", "-c:a", "aac", "-shortest", str(out))
    return out


@pytest.fixture(scope="session")
def _long_mp4(masters):
    _need("ffmpeg")
    out = masters / "long.mp4"
    _run("ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i",
         "testsrc2=size=1920x1080:rate=30:duration=30", "-f", "lavfi", "-i",
         "sine=duration=30", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
         "-shortest", str(out))
    return out


@pytest.fixture(scope="session")
def _png(masters):
    _need("magick")
    out = masters / "pic.png"
    _run("magick", "-size", "300x200", "gradient:red-blue", str(out))
    return out


@pytest.fixture(scope="session")
def _odt(masters, lo_profile):
    _need("soffice")
    txt = masters / "doc.txt"
    txt.write_text("Page one\fPage two\n")
    return _soffice(txt, "odt", lo_profile)


@pytest.fixture(scope="session")
def _pdf(_odt, lo_profile):
    return _soffice(_odt, "pdf", lo_profile)


@pytest.fixture(scope="session")
def _xlsx(masters, lo_profile):
    _need("soffice")
    csv = masters / "sheet.csv"
    csv.write_text("a,b\n1,2\n")
    return _soffice(csv, "xlsx", lo_profile)


@pytest.fixture(scope="session")
def _odp(_pdf, lo_profile):
    return _soffice(_pdf, "odp", lo_profile, "--infilter=impress_pdf_import")


def _copy(master: Path, tmp_path: Path) -> Path:
    return Path(shutil.copy2(master, tmp_path / master.name))


@pytest.fixture
def sample_wav(_wav, tmp_path): return _copy(_wav, tmp_path)
@pytest.fixture
def sample_mp4(_mp4, tmp_path): return _copy(_mp4, tmp_path)
@pytest.fixture
def long_mp4(_long_mp4, tmp_path): return _copy(_long_mp4, tmp_path)
@pytest.fixture
def sample_png(_png, tmp_path): return _copy(_png, tmp_path)
@pytest.fixture
def sample_odt(_odt, tmp_path): return _copy(_odt, tmp_path)
@pytest.fixture
def sample_pdf(_pdf, tmp_path): return _copy(_pdf, tmp_path)
@pytest.fixture
def sample_xlsx(_xlsx, tmp_path): return _copy(_xlsx, tmp_path)
@pytest.fixture
def sample_odp(_odp, tmp_path): return _copy(_odp, tmp_path)


@pytest.fixture
def samples(request):
    """Sample file for an input kind, e.g. ``samples("spreadsheet")``."""
    names = {"audio": "sample_wav", "video": "sample_mp4", "image": "sample_png",
             "document": "sample_odt", "spreadsheet": "sample_xlsx",
             "presentation": "sample_odp", "pdf": "sample_pdf"}
    return lambda kind: request.getfixturevalue(names[kind])


@pytest.fixture
def odd_names(_mp4, _png, _wav, tmp_path):
    """Samples renamed to break naive argument handling."""
    stem = "-lead [1] 100% naïve"
    return {kind: Path(shutil.copy2(src, tmp_path / f"{stem}{src.suffix}"))
            for kind, src in (("video", _mp4), ("image", _png), ("audio", _wav))}
