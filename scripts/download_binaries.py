"""
Standalone script to setup and download external binaries into bin/ folder.
Can be executed directly or called from setup.bat.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Configure utf-8 console output on Windows
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Add src to sys.path
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir / "src"))

from autovideo.core.binary_downloader import BinaryDownloader
from autovideo.core.binary_manager import BinaryManager


def main() -> None:
    print("=================================================================")
    print("  BANCONTENT AUTO STUDIO - CAI DAT CONG CU NGOAI VI VAO BIN/    ")
    print("=================================================================\n")

    downloader = BinaryDownloader()
    results = downloader.setup_all(progress_cb=lambda msg: print(f"  [*] {msg}"))

    print("\n[*] Ket qua thiet lap cac cong cu trong bin/:")
    for name, res in results.items():
        status_label = "[OK - SAN SANG]" if res.installed else "[CANH BAO - THIEU]"
        print(f"  + {name:<10}: {status_label} ({res.message})")

    # Run BinaryManager to verify all
    mgr = BinaryManager()
    all_status = mgr.check_all()
    print("\n[*] Tinh trang nhan dien he thong sau khi thiet lap:")
    for name, info in all_status.items():
        state = "[OK]" if info.is_available else "[THIEU]"
        print(f"  - {name:<10}: {state} (v{info.version or 'unknown'}) [Nguon: {info.source}]")

    print("\n[XAC NHAN] Hoan tat quy trinh cai dat cong cu!")


if __name__ == "__main__":
    main()
