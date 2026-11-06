"""Offline-safe launch preparation for the Windows OCR GUI.

Creates a Python 3.10-3.12 virtual environment, installs pinned packages from
PyPI, and imports ONNX Runtime / RapidOCR. Only this package's .venv is changed.
The launch-only PATH filters Conda entries; Windows PATH is never edited.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
PY = VENV / "Scripts" / "python.exe"


def run(args: list[str], *, check: bool = True, quiet: bool = False) -> int:
    if not quiet:
        print("\n> " + " ".join(str(a) for a in args), flush=True)
    kwargs: dict = {}
    if quiet:
        kwargs.update(stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    proc = subprocess.run(args, cwd=ROOT, **kwargs)
    if check and proc.returncode != 0:
        raise RuntimeError(f"Command failed with exit code {proc.returncode}")
    return proc.returncode


def supported_interpreter() -> bool:
    v = sys.version_info
    return (
        sys.platform == "win32"
        and v.major == 3
        and 10 <= v.minor <= 12
        and struct.calcsize("P") == 8
    )


def clean_path() -> None:
    """Filter Conda from this process only, preventing DLL shadowing."""
    path = os.environ.get("PATH", "")
    bad = re.compile(r"(?:^|[\\/])(?:anaconda\d*|miniconda\d*|conda)(?:[\\/]|$)", re.I)
    parts = [p for p in path.split(os.pathsep) if p and not bad.search(p)]
    # Required by Python's venv launcher and normal Windows search behavior.
    systemroot = os.environ.get("SystemRoot", r"C:\Windows")
    parts.extend([systemroot, str(Path(systemroot) / "System32")])
    os.environ["PATH"] = os.pathsep.join(dict.fromkeys(parts))
    print("Conda was removed from PATH for this launch only.", flush=True)


def main() -> int:
    print(f"Project: {ROOT}", flush=True)
    print(f"Python creating/checking venv: {sys.executable}", flush=True)
    print(f"Version: {sys.version}", flush=True)
    print(f"Architecture: {struct.calcsize('P') * 8}-bit", flush=True)
    if not supported_interpreter():
        print(
            "\n[ERROR] Use 64-bit Python 3.10, 3.11 or 3.12 from python.org.\n"
            "Anaconda and other Python versions are not used by this program.\n"
            "Install Python 3.12 x64, then delete .venv and run start.bat again.",
            flush=True,
        )
        return 1

    clean_path()
    if not PY.is_file():
        print("Creating .venv ...", flush=True)
        if sys.base_prefix == sys.prefix:
            run([sys.executable, "-m", "venv", str(VENV)])
        else:
            base = Path(sys.base_prefix) / "python.exe"
            if not base.is_file():
                raise RuntimeError(f"Cannot find base Python: {base}")
            # The old venv may belong to another Python installation.
            for old in VENV.glob("pyvenv.cfg"):
                if f"home = {sys.base_prefix}" not in old.read_text(errors="ignore"):
                    raise RuntimeError(
                        "The existing .venv points to another Python installation. "
                        "Close this program, delete only .venv, then run start.bat again."
                    )
            run([str(base), "-m", "venv", "--upgrade", str(VENV)])
    print(f"Using isolated Python: {PY}", flush=True)
    run([str(PY), "-c", "import sys,struct; print(sys.version); print(sys.executable); assert sys.platform=='win32' and 10<=sys.version_info.minor<=12 and struct.calcsize('P')==8"])
    run([str(PY), "-m", "pip", "install", "--upgrade", "pip"])
    # Only this package's .venv is changed. No system or Anaconda packages.
    run([
        str(PY), "-m", "pip", "uninstall", "-y", "onnxruntime",
        "onnxruntime-gpu", "onnxruntime-directml", "msvc-runtime",
        "opencv-python-headless",
    ], check=False)
    run([str(PY), "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")])
    print("Checking OCR imports before opening the page ...", flush=True)
    run([str(PY), str(ROOT / "diagnostic_environment.py")])
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BaseException:
        traceback.print_exc()
        raise SystemExit(1)
