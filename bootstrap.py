"""Install dependencies into the bundled Python (python\\Lib\\site-packages)."""
import hashlib, os, subprocess, sys
ROOT = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
MARK = os.path.join(ROOT, "python", ".deps_installed")
REQ = os.path.join(ROOT, "requirements.txt")

def run(args):
    print(">", " ".join(args), flush=True)
    return subprocess.call(args)

def main():
    print("Bundled Python:", PY, sys.version.split()[0])
    if not os.path.normcase(PY).startswith(os.path.normcase(os.path.join(ROOT, "python"))):
        print("[ERROR] Not running the bundled python. Use start.bat."); return 1
    try:
        import pip  # noqa
    except ImportError:
        if run([PY, os.path.join(ROOT, "get-pip.py"), "--no-warn-script-location"]) != 0:
            print("[ERROR] pip install failed (network?)"); return 1
    h = hashlib.sha256(open(REQ, "rb").read()).hexdigest()
    if not (os.path.exists(MARK) and open(MARK).read().strip() == h):
        for bad in ("onnxruntime-gpu", "onnxruntime-directml", "opencv-python-headless"):
            run([PY, "-m", "pip", "uninstall", "-y", bad])
        if run([PY, "-m", "pip", "install", "--no-warn-script-location", "-r", REQ]) != 0:
            print("[ERROR] Installing requirements failed."); return 1
        open(MARK, "w").write(h)
    diag = os.path.join(ROOT, "diagnostic_environment.py")
    if os.path.exists(diag) and run([PY, diag]) != 0:
        print("[ERROR] OCR runtime check failed. See diagnose_last.txt"); return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
