import os
import sys

# Ensure src/ is on sys.path
sys.path.insert(0, os.path.abspath("src"))

from autovideo.core.binary_manager import BinaryManager


def check_python_libraries():
    """Verify all required Python modules can be imported."""
    required = [
        ("FastAPI", "fastapi"),
        ("Uvicorn", "uvicorn"),
        ("Pydantic", "pydantic"),
        ("Mutagen (Audio Timing)", "mutagen"),
        ("Pillow (Thumbnails)", "PIL"),
        ("ZeroTTS (Voiceover)", "zerotts"),
        ("HTTPX (Async Network)", "httpx"),
        ("yt-dlp (Media Downloader)", "yt_dlp"),
        ("Pytest (Test Engine)", "pytest"),
    ]

    all_ok = True
    print("[*] Kiem tra cac thu vien Python can thiet:")
    for label, module_name in required:
        try:
            mod = __import__(module_name)
            ver = getattr(mod, "__version__", "san sang")
            print(f"  + {label:<28} : [OK] (v{ver})")
        except ImportError as e:
            print(f"  - {label:<28} : [THIEU] ({e})")
            all_ok = False
    return all_ok


def check_external_binaries():
    """Verify ffmpeg, ffprobe, yt-dlp, and BBDown binaries."""
    bm = BinaryManager()
    info = bm.check_all()

    print("\n[*] Kiem tra cac cong cu nhan dang trong bin/ va System PATH:")
    
    # ffmpeg
    ff = info.get("ffmpeg")
    if ff and ff.is_available:
        print(f"  + ffmpeg                     : [OK] ({ff.version}) [{ff.source}]")
    else:
        print("  - ffmpeg                     : [CANH BAO] Khong tim thay - Can co de render video")

    # ffprobe
    fp = info.get("ffprobe")
    if fp and fp.is_available:
        print(f"  + ffprobe                    : [OK] ({fp.version}) [{fp.source}]")
    else:
        print("  - ffprobe                    : [CANH BAO] Khong tim thay")

    # yt-dlp (binary or python module)
    yt = info.get("yt-dlp") or info.get("yt_dlp")
    if yt and yt.is_available:
        print(f"  + yt-dlp binary              : [OK] ({yt.version}) [{yt.source}]")
    else:
        print("  * yt-dlp binary              : [Chay qua Python package yt_dlp]")

    # BBDown (optional)
    bb = info.get("BBDown") or info.get("bbdown")
    if bb and bb.is_available:
        print(f"  + BBDown                     : [OK] ({bb.version}) [{bb.source}]")
    else:
        print("  * BBDown                     : [Tuy chon - Da co yt-dlp fallback cho Bilibili]")

    return bm.is_ready()


if __name__ == "__main__":
    libs_ok = check_python_libraries()
    bin_ok = check_external_binaries()
    print("\n" + "=" * 65)
    if libs_ok and bin_ok:
        print("[XAC NHAN] He thong da san sang 100% de khoi chay app!")
    else:
        print("[CANH BAO] Mot so thanh phan chua day du, xem chi tiet ben tren.")
    print("=" * 65)
