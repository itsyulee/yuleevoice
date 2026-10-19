import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
PYTHON = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def main():
    os.chdir(ROOT)

    if os.name == "nt":
        os.system("title Multi-Token-Voice Safe Launcher")
        os.system("cls")

    print("=" * 52)
    print("        MULTI-TOKEN VOICE LAUNCHER (Windows)")
    print("=" * 52)

    if not VENV.exists():
        print("[INFO] Dang tao moi truong ao (.venv)...")
        subprocess.run(
            [sys.executable, "-m", "venv", str(VENV)],
            check=True,
        )

        print("[INFO] Dang cai dat thu vien (lan dau)...")
        subprocess.run(
            [str(PYTHON), "-m", "pip", "install", "--upgrade", "pip"],
            check=True,
        )
        subprocess.run(
            [str(PYTHON), "-m", "pip", "install", "-r", "requirements.txt"],
            check=True,
        )
    else:
        print("[INFO] Phat hien moi truong ao san co.")

    print("[INFO] Dang khoi dong Bot...")
    print("-" * 52)
    subprocess.run([str(PYTHON), "dashboard.py"], check=True)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        print(f"\n[ERROR] Lenh dung voi ma loi: {error.returncode}")
    except KeyboardInterrupt:
        print("\n[INFO] Da nhan yeu cau dung.")
    except Exception as error:
        print(f"\n[ERROR] {error}")
    finally:
        print("-" * 52)
        print("[INFO] Bot da dung.")
        input("Nhan Enter de dong...")