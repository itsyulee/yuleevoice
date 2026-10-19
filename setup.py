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
    print("        MULTI-TOKEN VOICE LAUNCHER")
    print("=" * 52)

    # A copied/incomplete venv directory may exist without a usable interpreter.
    usable = False
    if PYTHON.is_file():
        try:
            result = subprocess.run(
                [str(PYTHON), "-c", "import sys; print(sys.version)"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=15,
            )
            usable = result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            pass

    if not usable:
        print("[INFO] Dang tao moi truong ao (.venv)...")
        subprocess.run(
            [sys.executable, "-m", "venv", str(VENV)],
            check=True,
        )

        if not PYTHON.is_file():
            raise RuntimeError("Khong tao duoc Python trong .venv. Kiem tra goi python3-venv tren host.")

    # Retry dependency installation after an interrupted or failed setup too.
    print("[INFO] Dang kiem tra va cai dat thu vien...")
    subprocess.run(
        [str(PYTHON), "-m", "pip", "install", "--upgrade", "pip"],
        check=True,
    )
    subprocess.run(
        [str(PYTHON), "-m", "pip", "install", "-r", "requirements.txt"],
        check=True,
    )

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
        if sys.stdin.isatty():
            input("Nhan Enter de dong...")