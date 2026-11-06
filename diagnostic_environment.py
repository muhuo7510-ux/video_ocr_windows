# -*- coding: utf-8 -*-
"""Local environment check before launching Video OCR.

Prints interpreter path, Python version, architecture, CPU brand (best-effort),
and whether onnxruntime / rapidocr_onnxruntime import. Writes the same text to
diagnose_last.txt in the working directory. No network, no upload, no secrets.
"""

from __future__ import annotations

import platform
import sys
import traceback
from pathlib import Path


def _out(lines: list[str], msg: str = "") -> None:
    print(msg)
    lines.append(msg)


def _cpu_brand() -> str:
    brand = platform.processor() or ""
    if sys.platform == "win32":
        try:
            import winreg  # type: ignore

            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
            )
            try:
                value, _ = winreg.QueryValueEx(key, "ProcessorNameString")
                if value:
                    brand = str(value).strip()
            finally:
                winreg.CloseKey(key)
        except Exception:
            pass
    return brand or "(unknown)"


def main() -> int:
    lines: list[str] = []
    _out(lines, "=== Video OCR environment diagnostic ===")
    _out(lines, f"sys.executable = {sys.executable}")
    _out(lines, f"Python = {sys.version.replace(chr(10), ' ')}")
    _out(lines, f"version_info = {sys.version_info[:3]}")
    _out(lines, f"platform = {platform.platform()}")
    _out(lines, f"architecture = {platform.architecture()}")
    _out(lines, f"machine = {platform.machine()}")
    _out(lines, f"cpu = {_cpu_brand()}")

    v = sys.version_info
    if not (v.major == 3 and 10 <= v.minor <= 12):
        _out(
            lines,
            "[WARN] Recommended Python is 3.10-3.12. Other versions may lack wheels.",
        )

    _out(lines, "--- import onnxruntime ---")
    try:
        import onnxruntime as ort  # noqa: WPS433

        _out(lines, f"onnxruntime OK version={getattr(ort, '__version__', '?')}")
        try:
            _out(lines, f"providers = {ort.get_available_providers()}")
        except Exception as e:  # pragma: no cover
            _out(lines, f"providers query failed: {type(e).__name__}: {e}")
    except Exception as e:
        _out(lines, f"onnxruntime IMPORT FAILED: {type(e).__name__}: {e}")
        _out(lines, traceback.format_exc().rstrip())
        _out(lines, "")
        _out(lines, "Actionable next steps:")
        _out(lines, "1) Re-run start.bat so it reinstalls pinned deps (onnxruntime==1.20.1).")
        _out(
            lines,
            "2) Install Microsoft Visual C++ Redistributable (x64) from Microsoft, then retry.",
        )
        _out(
            lines,
            "   https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist",
        )
        _out(
            lines,
            "3) If import still fails after VC++ update, this CPU/OS may be unsupported by",
        )
        _out(
            lines,
            "   this onnxruntime build. There is NO guarantee until diagnosed on your PC.",
        )
        _write(lines)
        return 1

    _out(lines, "--- import rapidocr_onnxruntime ---")
    try:
        from rapidocr_onnxruntime import RapidOCR  # noqa: F401,WPS433

        _out(lines, "rapidocr_onnxruntime OK")
    except Exception as e:
        _out(lines, f"rapidocr_onnxruntime IMPORT FAILED: {type(e).__name__}: {e}")
        _out(lines, traceback.format_exc().rstrip())
        _out(lines, "")
        _out(lines, "Actionable next steps: re-run start.bat; confirm Python 3.10-3.12;")
        _out(lines, "install VC++ x64 redistributable if DLL init still fails.")
        _write(lines)
        return 1

    _out(lines, "DIAGNOSTIC PASS")
    _write(lines)
    return 0


def _write(lines: list[str]) -> None:
    try:
        Path("diagnose_last.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("(also wrote diagnose_last.txt)")
    except Exception as e:
        print(f"(could not write diagnose_last.txt: {e})")


if __name__ == "__main__":
    raise SystemExit(main())
