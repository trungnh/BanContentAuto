"""
Settings Management and Persistence for BanContentAuto.
Manages user configurations in config/settings.json, environment variables,
cache maintenance, and external credentials (9router, Gemini, Douyin, Voiceover).
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

from autovideo.core.config import AppConfig, get_config

logger = logging.getLogger(__name__)


@dataclass
class UserSettings:
    """User-configurable settings persisted to config/settings.json."""

    # 9router Gateway & LLM Provider Configuration
    ninerouter_api_key: str = ""
    ninerouter_base_url: str = "http://localhost:20128/v1"
    llm_provider: str = "9router"  # "9router" or "gemini" or "mock"
    llm_model: str = "antigravity/claude-3-5-sonnet"
    cached_models: List[str] = field(default_factory=lambda: [
        "antigravity/claude-3-5-sonnet",
        "codex/gpt-4o",
        "codex/o3-mini",
        "gemini-2.0-flash",
        "gemini-1.5-pro",
    ])

    # Thumbnail & Image Generation (9router Text-to-Image)
    image_provider: str = "9router"  # "9router" | "none"
    image_model: str = "ag/gemini-3.8-flash"

    # Direct Gemini API (Fallback)
    gemini_api_key: str = ""

    # Semantic Footage Judge (ADR-019): multimodal LLM checks sampled frames against narration
    semantic_judge_enabled: bool = True
    semantic_judge_model: str = ""  # empty -> reuse llm_model
    semantic_judge_min_score: int = 5  # 0-10 (calibrated on proj_f2668146: off-topic=0, generic-correct=3-5)
    semantic_judge_reject_overlays: bool = True
    footage_max_reuse: int = 2  # max scenes per single source video

    # TTS Providers & Voiceover Architecture (ZeroTTS, Maziao Cloud, Edge-TTS)
    tts_primary_provider: str = "zerotts"  # "zerotts" | "maziao" | "edge_tts"
    tts_enable_fallback: bool = True

    # ZeroTTS (Offline CPU, $0 Invariant)
    zerotts_voice: str = "banmai"  # banmai, maichi, minhquang, thientam
    zerotts_comma_pause_ms: int = 200
    zerotts_period_pause_ms: int = 400

    # Maziao Cloud TTS (docs/maziao.md)
    maziao_api_key: str = ""
    maziao_base_url: str = "https://app.maziao.com"
    maziao_model_id: str = "lingual_speech_v2"  # lingual_speech_v2 | vieten_speech
    maziao_voice_id: str = "zv_vi_sg_male_thien_tam"
    maziao_volume: float = 1.0
    maziao_pitch: float = 1.0

    # Edge-TTS (Free Microsoft Neural Cloud)
    edge_tts_voice: str = "vi-VN-HoaiMyNeural"

    # Douyin Sourcing & Jitter
    douyin_cookie: str = ""
    jitter_min_sec: float = 2.0
    jitter_max_sec: float = 5.0

    # Audio & Voiceover General
    default_voice: str = "vi-VN-HoaiMyNeural"
    speech_rate: float = 1.0
    target_lufs: float = -14.0

    # Rendering & Rolling Buffer
    rolling_buffer_max_gb: float = 5.0
    render_concurrency: int = 2
    clean_intermediate_parts: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> UserSettings:
        valid_keys = {f for f in cls.__dataclass_fields__}
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)


class SettingsManager:
    """Manages loading, updating, persisting settings, and disk cache maintenance."""

    def __init__(self, config: Optional[AppConfig] = None) -> None:
        self.config = config or get_config()
        self.config.paths.ensure_directories()
        self._settings_file = self.config.paths.config_dir / "settings.json"
        self._settings = self._load()

    def _load(self) -> UserSettings:
        """Loads settings from config/settings.json, falling back to env/defaults."""
        settings = UserSettings()

        # 1. Fallback to existing environment variables
        env_nr_key = os.getenv("NINEROUTER_API_KEY") or os.getenv("NINE_ROUTER_API_KEY", "")
        if env_nr_key:
            settings.ninerouter_api_key = env_nr_key

        env_nr_url = os.getenv("NINEROUTER_BASE_URL")
        if env_nr_url:
            settings.ninerouter_base_url = env_nr_url

        env_gemini = os.getenv("GEMINI_API_KEY", "")
        if env_gemini:
            settings.gemini_api_key = env_gemini

        # 2. Check for douyin cookies in cookies.txt
        cookies_txt = self.config.paths.config_dir / "cookies.txt"
        if cookies_txt.exists():
            try:
                settings.douyin_cookie = cookies_txt.read_text(encoding="utf-8").strip()
            except Exception:
                pass

        # 3. Read settings.json if present
        if self._settings_file.exists():
            try:
                content = self._settings_file.read_text(encoding="utf-8")
                data = json.loads(content)
                if isinstance(data, dict):
                    settings = UserSettings.from_dict(data)
            except Exception as e:
                logger.warning(f"Could not read settings from {self._settings_file}: {e}")

        # Sync runtime config limits
        self._apply_to_config(settings)
        return settings

    def get_settings(self) -> UserSettings:
        """Returns the current loaded user settings."""
        return self._settings

    load_settings = get_settings

    def _apply_to_config(self, settings: UserSettings) -> None:
        """Synchronizes UserSettings into the runtime AppConfig and environment."""
        if settings.ninerouter_api_key:
            os.environ["NINEROUTER_API_KEY"] = settings.ninerouter_api_key
        if settings.ninerouter_base_url:
            os.environ["NINEROUTER_BASE_URL"] = settings.ninerouter_base_url
        if settings.gemini_api_key:
            os.environ["GEMINI_API_KEY"] = settings.gemini_api_key
        if settings.maziao_api_key:
            os.environ["MAZIAO_API_KEY"] = settings.maziao_api_key

        self.config.performance.rolling_buffer_max_gb = settings.rolling_buffer_max_gb
        self.config.performance.render_concurrency = settings.render_concurrency
        self.config.performance.clean_intermediate_parts = settings.clean_intermediate_parts
        self.config.sourcing.jitter_min_sec = settings.jitter_min_sec
        self.config.sourcing.jitter_max_sec = settings.jitter_max_sec
        self.config.compliance.target_lufs = settings.target_lufs

    def save_settings(self, updates: Dict[str, Any]) -> UserSettings:
        """
        Updates and persists settings to config/settings.json and syncs env/cookies.
        Preserves existing API keys if masked strings are provided.
        """
        current_dict = self._settings.to_dict()

        for key, val in updates.items():
            if val is None:
                continue
            # If the user did not change a masked API key, do not overwrite with asterisks
            if key in ("gemini_api_key", "ninerouter_api_key", "maziao_api_key") and ("***" in str(val) or "..." in str(val)):
                continue
            if key in current_dict:
                expected_type = type(current_dict[key])
                try:
                    current_dict[key] = expected_type(val)
                except (ValueError, TypeError):
                    current_dict[key] = val

        self._settings = UserSettings.from_dict(current_dict)
        self._apply_to_config(self._settings)

        # Write to settings.json
        self.config.paths.config_dir.mkdir(parents=True, exist_ok=True)
        self._settings_file.write_text(
            json.dumps(self._settings.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        # Write douyin cookie to cookies.txt if provided
        if self._settings.douyin_cookie:
            cookies_file = self.config.paths.config_dir / "cookies.txt"
            cookies_file.write_text(self._settings.douyin_cookie, encoding="utf-8")

        return self._settings

    def get_masked_settings(self) -> Dict[str, Any]:
        """Returns settings dictionary with sensitive credentials masked for the UI."""
        data = self._settings.to_dict()

        # 1. Mask 9router API key
        nr_key = self._settings.ninerouter_api_key
        if nr_key and len(nr_key) > 8:
            data["ninerouter_api_key_masked"] = nr_key[:4] + "*" * (len(nr_key) - 8) + nr_key[-4:]
        elif nr_key:
            data["ninerouter_api_key_masked"] = "****"
        else:
            data["ninerouter_api_key_masked"] = ""
        data["has_ninerouter_key"] = bool(nr_key)
        data["ninerouter_base_url"] = self._settings.ninerouter_base_url or "http://localhost:20128/v1"

        # 2. Mask Gemini API key
        key = self._settings.gemini_api_key
        if key and len(key) > 8:
            data["gemini_api_key_masked"] = key[:4] + "*" * (len(key) - 8) + key[-4:]
        elif key:
            data["gemini_api_key_masked"] = "****"
        else:
            data["gemini_api_key_masked"] = ""
        data["has_gemini_key"] = bool(key)

        # 3. Mask Maziao API key
        mz_key = self._settings.maziao_api_key
        if mz_key and len(mz_key) > 8:
            data["maziao_api_key_masked"] = mz_key[:4] + "*" * (len(mz_key) - 8) + mz_key[-4:]
        elif mz_key:
            data["maziao_api_key_masked"] = "****"
        else:
            data["maziao_api_key_masked"] = ""
        data["has_maziao_key"] = bool(mz_key)

        # 4. Douyin cookie preview
        data["has_douyin_cookie"] = bool(self._settings.douyin_cookie.strip())
        if self._settings.douyin_cookie:
            c = self._settings.douyin_cookie.strip()
            data["douyin_cookie_preview"] = (c[:30] + "...") if len(c) > 30 else c
        else:
            data["douyin_cookie_preview"] = ""

        # 5. Cached models list
        data["cached_models"] = self._settings.cached_models or [
            "antigravity/claude-3-5-sonnet",
            "codex/gpt-4o",
            "codex/o3-mini",
            "gemini-2.0-flash",
            "gemini-1.5-pro",
        ]

        # 6. Include cache usage breakdown
        data["cache_breakdown"] = self.get_cache_usage()

        return data

    def fetch_ninerouter_models(
        self, base_url: Optional[str] = None, api_key: Optional[str] = None
    ) -> Tuple[bool, str, List[str]]:
        """
        Connects to 9router at {base_url}/models and retrieves available models.
        Returns (success: bool, message: str, models: list[str]).
        """
        url_to_use = (base_url or self._settings.ninerouter_base_url or "http://localhost:20128/v1").rstrip("/")
        key_to_use = api_key if (api_key is not None and not "***" in str(api_key)) else (
            self._settings.ninerouter_api_key or os.getenv("NINEROUTER_API_KEY", "")
        )

        # Mock / Test key handler for tests and offline environments
        if key_to_use and (key_to_use.startswith("mock_") or key_to_use == "test_key"):
            mock_models = [
                "antigravity/claude-3-5-sonnet",
                "antigravity/claude-3-haiku",
                "codex/gpt-4o",
                "codex/gpt-4o-mini",
                "codex/o3-mini",
                "gemini-2.0-flash",
                "gemini-1.5-pro",
            ]
            self.save_settings({"cached_models": mock_models, "ninerouter_base_url": url_to_use})
            return True, f"Kết nối 9Router thành công! Đã tải {len(mock_models)} mô hình (Offline Mock Mode).", mock_models

        headers = {"Accept": "application/json"}
        if key_to_use:
            headers["Authorization"] = f"Bearer {key_to_use}"

        try:
            models_url = f"{url_to_use}/models"
            with httpx.Client(timeout=8.0) as client:
                resp = client.get(models_url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    raw_items = data.get("data", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
                    model_ids = []
                    for item in raw_items:
                        if isinstance(item, dict) and "id" in item:
                            model_ids.append(item["id"])
                        elif isinstance(item, str):
                            model_ids.append(item)

                    if not model_ids:
                        return False, "9Router không trả về mô hình nào khả dụng.", []

                    # Save models to cache
                    self.save_settings({"cached_models": model_ids, "ninerouter_base_url": url_to_use})
                    return True, f"Đã kết nối 9Router và nạp {len(model_ids)} mô hình khả dụng!", model_ids
                elif resp.status_code in (401, 403):
                    return False, f"9Router từ chối xác thực (Mã {resp.status_code}): Vui lòng kiểm tra 9Router API Key.", []
                else:
                    return False, f"9Router phản hồi mã lỗi {resp.status_code}: {resp.text[:120]}", []
        except httpx.ConnectError:
            return False, f"Không thể kết nối đến 9Router tại {url_to_use}. Vui lòng kiểm tra dịch vụ 9Router đã khởi động chưa.", []
        except Exception as e:
            return False, f"Lỗi khi kết nối 9Router: {str(e)}", []

    def get_cache_usage(self) -> Dict[str, float]:
        """Calculates current disk usage across cache directories in MB."""
        def dir_size_mb(path: Path) -> float:
            if not path.exists():
                return 0.0
            total_bytes = 0
            for p in path.rglob("*"):
                if p.is_file():
                    total_bytes += p.stat().st_size
            return round(total_bytes / (1024 * 1024), 2)

        audio_mb = dir_size_mb(self.config.paths.cache_audio_dir)
        footage_mb = dir_size_mb(self.config.paths.cache_raw_footage_dir)
        scenes_mb = dir_size_mb(self.config.paths.cache_temp_scenes_dir)
        total_mb = round(audio_mb + footage_mb + scenes_mb, 2)

        return {
            "audio_mb": audio_mb,
            "raw_footage_mb": footage_mb,
            "temp_scenes_mb": scenes_mb,
            "total_mb": total_mb,
        }

    def clear_cache(self) -> Dict[str, Any]:
        """
        Safely clears intermediate temporary files in cache subdirectories.
        Leaves directories intact. Returns freed MB and count of files removed.
        """
        target_dirs = [
            self.config.paths.cache_audio_dir,
            self.config.paths.cache_raw_footage_dir,
            self.config.paths.cache_raw_assets_dir,
            self.config.paths.cache_temp_scenes_dir,
        ]

        freed_bytes = 0
        files_removed = 0

        for d in target_dirs:
            if not d.exists():
                continue
            for item in d.iterdir():
                try:
                    if item.is_file():
                        freed_bytes += item.stat().st_size
                        item.unlink()
                        files_removed += 1
                    elif item.is_dir():
                        for sub_f in item.rglob("*"):
                            if sub_f.is_file():
                                freed_bytes += sub_f.stat().st_size
                        shutil.rmtree(item, ignore_errors=True)
                        files_removed += 1
                except Exception as e:
                    logger.warning(f"Error removing cache file {item}: {e}")

        freed_mb = round(freed_bytes / (1024 * 1024), 2)
        return {
            "success": True,
            "freed_bytes": freed_bytes,
            "freed_mb": freed_mb,
            "files_removed": files_removed,
        }

    def test_gemini_api(self, api_key: Optional[str] = None) -> Tuple[bool, str]:
        """
        Tests Gemini API connectivity using the provided key or configured key.
        Handles offline/mock modes gracefully.
        """
        key_to_test = api_key or self._settings.gemini_api_key or os.getenv("GEMINI_API_KEY", "")
        if not key_to_test:
            return False, "Chưa nhập Gemini API Key. Vui lòng nhập API Key để sử dụng Google Gemini."

        if key_to_test.startswith("mock_") or key_to_test == "test_key":
            return True, "Mock API Key hợp lệ (Chế độ kiểm thử thành công)."

        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key_to_test}"
            with httpx.Client(timeout=8.0) as client:
                resp = client.get(url)
                if resp.status_code == 200:
                    models = resp.json().get("models", [])
                    return True, f"Kết nối Google Gemini thành công! Tìm thấy {len(models)} mô hình khả dụng."
                elif resp.status_code in (400, 403):
                    return False, f"Google Gemini API từ chối: Khóa API không hợp lệ hoặc bị giới hạn quyền ({resp.status_code})."
                else:
                    return False, f"Google Gemini phản hồi mã lỗi {resp.status_code}: {resp.text[:100]}"
        except httpx.ConnectTimeout:
            return False, "Hết thời gian chờ kết nối đến Google Generative Language API (Vui lòng kiểm tra mạng/proxy)."
        except Exception as e:
            return False, f"Lỗi kết nối khi gọi Gemini API: {str(e)}"

    def test_maziao_api(
        self, api_key: Optional[str] = None, base_url: Optional[str] = None
    ) -> Tuple[bool, str]:
        """Validates Maziao TTS API credentials and endpoint connectivity (docs/maziao.md)."""
        key_to_use = api_key.strip() if (api_key is not None and api_key.strip() and not "***" in str(api_key)) else (
            self._settings.maziao_api_key or os.getenv("MAZIAO_API_KEY", "")
        )
        primary_url = (base_url or self._settings.maziao_base_url or "https://app.maziao.com").rstrip("/")

        if not key_to_use:
            return False, "Chưa nhập Maziao API Key. Vui lòng cung cấp API Key để sử dụng Maziao TTS."

        if key_to_use.startswith("mock_") or key_to_use == "test_key":
            return True, "Mock API Key hợp lệ (Kiểm thử kết nối Maziao TTS thành công!)."

        # Candidate endpoints to try (supporting app.maziao.com and maziao.com)
        candidate_urls = [primary_url]
        for fallback in ["https://app.maziao.com", "https://maziao.com"]:
            if fallback not in candidate_urls:
                candidate_urls.append(fallback)

        headers = {
            "Authorization": f"Bearer {key_to_use}",
            "x-api-key": key_to_use,
            "Accept": "application/json",
        }

        last_error = ""
        for url in candidate_urls:
            try:
                with httpx.Client(timeout=8.0) as client:
                    resp = client.get(f"{url}/api/voices?limit=1", headers=headers)
                    if resp.status_code in (200, 201):
                        return True, f"Kết nối Maziao Cloud TTS ({url}) thành công! API Key hợp lệ."
                    elif resp.status_code in (401, 403):
                        try:
                            err_data = resp.json()
                            if isinstance(err_data, dict) and err_data.get("errors"):
                                return False, f"Maziao từ chối xác thực ({resp.status_code}): {', '.join(err_data['errors'])}"
                        except Exception:
                            pass
                        return False, f"Maziao API từ chối xác thực ({resp.status_code}): Vui lòng kiểm tra lại Maziao API Key."
                    else:
                        last_error = f"Máy chủ {url} phản hồi mã lỗi {resp.status_code}: {resp.text[:120]}"
            except httpx.ConnectError:
                last_error = f"Không thể kết nối đến máy chủ {url} (Lỗi kết nối mạng)."
            except httpx.ConnectTimeout:
                last_error = f"Hết thời gian chờ khi kết nối đến máy chủ {url}."
            except Exception as e:
                last_error = f"Lỗi kiểm tra tại {url}: {str(e)}"

        return False, last_error or "Không thể xác thực Maziao API Key. Vui lòng kiểm tra lại mạng hoặc khóa API."

    def get_zerotts_voices(self) -> List[Dict[str, Any]]:
        """Retrieves official ZeroTTS voices plus any user-installed cloned voice packs."""
        official_presets = [
            {"id": "maichi", "name": "Mai Chi (Nữ - Kể chuyện nhẹ nhàng, truyền cảm)", "gender": "Nữ", "desc": "Kể chuyện nhẹ nhàng, truyền cảm", "is_cloned": False},
            {"id": "baotrang", "name": "Bảo Trang (Nữ - Tin tức rõ ràng, trung tính)", "gender": "Nữ", "desc": "Tin tức rõ ràng, trung tính", "is_cloned": False},
            {"id": "kimoanh", "name": "Kim Oanh (Nữ - Kể chuyện ấm áp, sâu lắng)", "gender": "Nữ", "desc": "Kể chuyện ấm áp, sâu lắng", "is_cloned": False},
            {"id": "giahuy", "name": "Gia Huy (Nam - Kể chuyện trầm ấm, tâm tình)", "gender": "Nam", "desc": "Kể chuyện trầm ấm, tâm tình", "is_cloned": False},
            {"id": "huuduc", "name": "Hữu Đức (Nam - Lớn tuổi, điềm đạm)", "gender": "Nam", "desc": "Lớn tuổi, điềm đạm", "is_cloned": False},
            {"id": "quangminh", "name": "Quang Minh (Nam - Tin tức rõ ràng, dứt khoát)", "gender": "Nam", "desc": "Tin tức rõ ràng, dứt khoát", "is_cloned": False},
            {"id": "tiendat", "name": "Tiến Đạt (Nam - Sôi nổi, bình luận cuốn hút)", "gender": "Nam", "desc": "Sôi nổi, bình luận cuốn hút", "is_cloned": False},
            {"id": "hamy", "name": "Hà My (Nữ - Hoạt hình, biểu cảm cao)", "gender": "Nữ", "desc": "Hoạt hình, biểu cảm cao", "is_cloned": False},
        ]

        cloned_voices: List[Dict[str, Any]] = []
        try:
            from zerotts.voices import USER_VOICES_DIR
            if USER_VOICES_DIR.is_dir():
                for vdir in sorted(USER_VOICES_DIR.iterdir()):
                    if vdir.is_dir() and (vdir / "voice.npz").exists():
                        meta_file = vdir / "meta.json"
                        meta = {}
                        if meta_file.exists():
                            try:
                                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                            except Exception:
                                pass
                        name = vdir.name
                        display_name = meta.get("display_name") or name.replace("_", " ").title()
                        gender = meta.get("gender", "Tùy chỉnh")
                        desc = meta.get("description", "Giọng clone cá nhân")
                        cloned_voices.append({
                            "id": name,
                            "name": f"👑 {display_name} (Clone)",
                            "gender": gender,
                            "desc": desc,
                            "is_cloned": True,
                        })
        except Exception as e:
            logger.debug(f"Error querying user voices: {e}")

        return cloned_voices + official_presets

    def install_zerotts_clone_voice(
        self, file_bytes: bytes, file_name: str
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """Installs a ZeroTTS voice pack (.zip or .npz) into USER_VOICES_DIR (~/.zerotts/voices/)."""
        try:
            from zerotts.voices import USER_VOICES_DIR, install_voice_zip
            USER_VOICES_DIR.mkdir(parents=True, exist_ok=True)

            if file_name.lower().endswith(".zip"):
                temp_zip = self.config.paths.cache_dir / f"temp_{file_name}"
                temp_zip.write_bytes(file_bytes)
                try:
                    installed = install_voice_zip(temp_zip, dest_root=USER_VOICES_DIR)
                    if not installed:
                        return False, "Tệp zip không chứa voice pack hợp lệ (cần thư mục chứa voice.npz).", None
                    installed_name = list(installed.keys())[0]
                    vdir = installed[installed_name]
                    meta = {}
                    if (vdir / "meta.json").exists():
                        try:
                            meta = json.loads((vdir / "meta.json").read_text(encoding="utf-8"))
                        except Exception:
                            pass
                    voice_info = {
                        "id": installed_name,
                        "name": f"👑 {meta.get('display_name') or installed_name} (Clone)",
                        "gender": meta.get("gender", "Tùy chỉnh"),
                        "desc": meta.get("description", "Giọng clone cá nhân"),
                        "is_cloned": True,
                    }
                    return True, f"Đã cài đặt giọng clone '{installed_name}' vào ZeroTTS thành công!", voice_info
                finally:
                    if temp_zip.exists():
                        temp_zip.unlink(missing_ok=True)

            elif file_name.lower().endswith(".npz"):
                stem_name = Path(file_name).stem.replace("voice", "").strip("_-") or "custom_voice"
                safe_name = "".join(c for c in stem_name if c.isalnum() or c in "._- ").strip() or "cloned_voice"
                target_dir = USER_VOICES_DIR / safe_name
                target_dir.mkdir(parents=True, exist_ok=True)
                (target_dir / "voice.npz").write_bytes(file_bytes)
                meta = {
                    "display_name": safe_name.replace("_", " ").title(),
                    "gender": "Tùy chỉnh",
                    "description": "Giọng clone được tải lên trực tiếp từ file .npz",
                    "language": "vi",
                }
                (target_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
                voice_info = {
                    "id": safe_name,
                    "name": f"👑 {meta['display_name']} (Clone)",
                    "gender": "Tùy chỉnh",
                    "desc": meta["description"],
                    "is_cloned": True,
                }
                return True, f"Đã cài đặt giọng clone '{safe_name}' vào ZeroTTS thành công!", voice_info
            else:
                return False, "Định dạng không hỗ trợ. Vui lòng tải lên tệp .zip hoặc .npz của ZeroTTS.", None
        except Exception as e:
            logger.exception("Error installing clone voice: %s", e)
            return False, f"Lỗi khi cài đặt giọng clone: {str(e)}", None

    def fetch_maziao_voices(
        self, api_key: Optional[str] = None, base_url: Optional[str] = None
    ) -> Tuple[bool, str, List[Dict[str, Any]]]:
        """Fetches voices list from Maziao Cloud TTS (my-voices + public/system voices)."""
        key_to_use = api_key.strip() if (api_key is not None and api_key.strip() and not "***" in str(api_key)) else (
            self._settings.maziao_api_key or os.getenv("MAZIAO_API_KEY", "")
        )
        primary_url = (base_url or self._settings.maziao_base_url or "https://app.maziao.com").rstrip("/")

        default_vi_voices = [
            {"id": "zv_vi_sg_male_thien_tam", "name": "🇻🇳 Thiện Tâm (Nam Nam - Đĩnh đạc)", "language": "vi", "gender": "male", "is_cloned": False},
            {"id": "zv_vi_hn_female_ngoc_huyen", "name": "🇻🇳 Ngọc Huyền (Nữ Bắc - Tự nhiên)", "language": "vi", "gender": "female", "is_cloned": False},
            {"id": "zv_vi_hn_male_duc_manh", "name": "🇻🇳 Đức Mạnh (Nam Bắc - Trầm ấm)", "language": "vi", "gender": "male", "is_cloned": False},
            {"id": "0KdW9bPh6HNMCxJV1GXF0", "name": "🌐 Ethan (English - Professional)", "language": "en", "gender": "male", "is_cloned": False},
        ]

        if key_to_use.startswith("mock_") or key_to_use == "test_key":
            mock_cloned = [
                {"id": "mv_cloned_my_voice_01", "name": "👑 Giọng Clone Của Bạn 01 (Mock)", "language": "vi", "gender": "custom", "is_cloned": True},
            ]
            return True, "Lấy danh sách giọng Maziao thành công (Mock Mode)!", mock_cloned + default_vi_voices

        candidate_urls = [primary_url]
        for fb in ["https://app.maziao.com", "https://maziao.com"]:
            if fb not in candidate_urls:
                candidate_urls.append(fb)

        headers = {
            "Authorization": f"Bearer {key_to_use}" if key_to_use else "",
            "x-api-key": key_to_use if key_to_use else "",
            "Accept": "application/json",
        }

        all_voices: List[Dict[str, Any]] = []
        my_voices: List[Dict[str, Any]] = []

        if key_to_use:
            try:
                with httpx.Client(timeout=8.0) as client:
                    resp = client.get(f"{primary_url}/api/voices/my-voices", headers=headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        raw_my = data.get("data", {}).get("items", []) if isinstance(data.get("data"), dict) else data.get("voices", [])
                        for item in raw_my:
                            vid = item.get("id") or item.get("voiceId")
                            vname = item.get("name") or vid
                            if vid:
                                my_voices.append({
                                    "id": vid,
                                    "name": f"👑 {vname} (Clone)",
                                    "language": item.get("language", "vi"),
                                    "gender": item.get("gender", "custom"),
                                    "is_cloned": True,
                                })
            except Exception:
                pass

        for url in candidate_urls:
            try:
                with httpx.Client(timeout=8.0) as client:
                    resp = client.get(f"{url}/api/voices?limit=100", headers=headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        raw_items = data.get("voices", [])
                        if not raw_items and isinstance(data.get("data"), dict):
                            raw_items = data["data"].get("items", [])
                        elif not raw_items and isinstance(data.get("data"), list):
                            raw_items = data["data"]

                        for item in raw_items:
                            vid = item.get("id") or item.get("voiceId")
                            if not vid:
                                continue
                            vname = item.get("name") or vid
                            lang = item.get("language", "vi")
                            gender = item.get("gender", "male")
                            flag = "🇻🇳" if lang == "vi" else "🌐"
                            all_voices.append({
                                "id": vid,
                                "name": f"{flag} {vname} ({lang.upper()} - {gender})",
                                "language": lang,
                                "gender": gender,
                                "is_cloned": False,
                            })
                        break
            except Exception:
                pass

        if my_voices or all_voices:
            vi_voices = [v for v in all_voices if v.get("language") == "vi"]
            other_voices = [v for v in all_voices if v.get("language") != "vi"]
            combined = my_voices + vi_voices + other_voices
            return True, f"Đã nạp {len(combined)} giọng từ Maziao Cloud!", combined

        return True, "Đã nạp danh sách giọng mặc định của Maziao!", default_vi_voices

    def setup_binaries(self) -> Dict[str, Any]:
        """Downloads or copies all missing external binaries into bin/."""
        from autovideo.core.binary_downloader import BinaryDownloader
        from autovideo.core.binary_manager import BinaryManager

        downloader = BinaryDownloader(config=self.config)
        results = downloader.setup_all()
        mgr = BinaryManager(config=self.config)
        statuses = mgr.check_all()

        return {
            "success": True,
            "message": "Đã thiết lập toàn bộ công cụ ngoại vi vào bin/ thành công!",
            "details": {k: {"installed": v.installed, "message": v.message} for k, v in results.items()},
            "binaries": {k: v.to_dict() for k, v in statuses.items()},
        }
