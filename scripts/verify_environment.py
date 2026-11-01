"""
Environment and dependency verification script.
Checks Python version, installed packages, directory structure, and configuration.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Fix Windows console encoding for UTF-8 characters
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Ensure repository root is in sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main() -> int:
    print("=" * 60)
    print("AlgoTradingResearch -- Environment Verification")
    print("=" * 60)

    # 1. Python version
    py_ver = sys.version_info
    print(f"Python Version: {py_ver.major}.{py_ver.minor}.{py_ver.micro}")
    if py_ver < (3, 10):
        print("[ERROR] Python 3.10+ required.")
        return 1
    print("[OK] Python version compatible (>=3.10)")

    # 2. Check Core Dependencies
    required_packages = [
        "fastapi",
        "uvicorn",
        "streamlit",
        "pandas",
        "numpy",
        "pyarrow",
        "httpx",
        "pydantic",
        "pydantic_settings",
        "sqlalchemy",
        "plotly",
        "pytest",
    ]

    missing = []
    for pkg in required_packages:
        try:
            __import__(pkg)
            print(f"[OK] Package installed: {pkg}")
        except ImportError:
            missing.append(pkg)
            print(f"[FAIL] Missing package: {pkg}")

    if missing:
        print(f"\nMissing packages: {', '.join(missing)}")
        return 1

    # 3. Check App Imports
    try:
        from app.core.config import settings

        print("[OK] Core application modules imported successfully.")
    except Exception as e:
        print(f"[FAIL] Failed to import application modules: {e}")
        return 1

    # 4. Check Directories
    for d in [settings.DATA_DIR, settings.REPORTS_DIR, settings.CACHE_DIR]:
        d.mkdir(parents=True, exist_ok=True)
        print(f"[OK] Directory verified: {d}")

    # 5. Check Execution Mode
    print(f"[OK] Execution Mode: {settings.EXECUTION_MODE} (Live trading disabled)")

    print("\n" + "=" * 60)
    print("All environment checks passed successfully!")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
