"""
Universal multi-platform video downloader using yt-dlp.
Supports YouTube, Pexels, Pixabay, Archive.org, and generic stream URLs.
Enforces duration filtering (8s-60s) per REQ-B2-02.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yt_dlp

from autovideo.core.binary_manager import BinaryManager
from autovideo.core.config import AppConfig, get_config
from autovideo.sourcing.relevance import anchor_head, anchor_matches, matched_scene_terms

logger = logging.getLogger(__name__)

# Strict default negative terms to reject human news, TV broadcasts, fiction movies, cartoons, reaction vlogs, subscribe bumpers, zoos, human babies, 3D asset stores, and stock previews
DEFAULT_NEGATIVE_TERMS: List[str] = [
    # Human News / TV Broadcasts / Social Media News
    "news", "breaking news", "bản tin", "thời sự", "vtc", "vtv", "vtv1", "vtv2", "vtv3",
    "htv", "htv7", "htv9", "thvl", "thvl1", "thvl2", "truyền hình", "chuyển động 24h", "60 giây", "60s",
    "cgtn", "cctv", "swns", "reuters", "cnn", "bbc news", "phóng sự", "newscast", "anchor", "news report", "báo thanh niên", "tuổi trẻ", "vnews",
    # Feature Films / Hollywood Fiction
    "full movie", "movieclip", "fandango", "trailer", "film clip", "cinema", "feature film",
    # Cartoons / Kids Animation / Educational Stickman
    "cartoon", "kids animation", "cartoon animation", "2d cartoon", "mầm non", "thiếu nhi", "nursery", "baby bus", "cocomelon", "minuteearth", "drawing", "stickman", "greenscreen", "green screen",
    # Reactions / Webcam Vlog / Facecam / Audio Only / Sound Clips
    "reaction", "reacting", "vlog", "review", "webcam", "facecam", "podcast", "interview", "unboxing", "live stream", "sound effect", "animal sounds", "animoo",
    # Captive Zoos / Enclosures / Cages
    "zoo", "zoological", "enclosure", "caged", "behind fence", "behind glass", "sanctuary park",
    # Human infants / babies (prevents returning human infants on queries like 'con non' or 'newborn')
    "human baby", "infant", "newborn baby", "toddler",
    # YouTube End Cards, Outros, Subscribe Animations
    "subscribe", "subscriber", "subscribers", "like and subscribe", "outro", "end screen", "intro bumper",
    # 3D Asset Marketplaces / CGI Showcases / Wireframes
    "3d model", "turbosquid", "cgtrader", "sketchfab", "promax3d", "rigged", "vfx asset", "blender model",
    "unreal engine asset", "unity asset", "wireframe", "free 3d", "download 3d", "3d asset",
    # Stock Footage Preview Agencies (Watermarked previews)
    "shutterstock", "getty images", "istock", "pond5", "storyblocks", "alamy", "watermark", "preview only", "watermarked",
    # Explainer / Talking Head / Hardcoded Captions / Lectures
    "explained", "talking head", "presentation", "tutorial", "lecture", "educational video",
    # Hardcoded Subtitles & Captions
    "subtitles", "with subtitles", "closed captions", "captioned", "subbed", "lyric video",
    # TV Screen / Off-screen Phone Recordings
    "tv screen", "filmed from tv", "filmed off tv", "recording tv", "on television", "screen recording", "recording screen", "recorded from tv", "cell phone recording",
    # Disney / Cartoons / Fiction Animations
    "disney", "lion king", "the lion king", "pixar", "dreamworks", "animated series",
    # Equipment Promos / Instructional / Demo / Commercials
    "accessories", "demo video", "demonstration", "promotional", "promo video", "commercial video", "product review",
    # Irrelevant Industrial & Machinery testing
    "machinery test", "pipe inspection", "industrial robot", "drill testing",
]

# Clean wildlife, safari, and nature channels that typically provide raw, unbranded b-roll
TRUSTED_DOC_CHANNELS: List[str] = [
    "safari", "wild earth", "kruger", "wildlife sightings", "nature footage",
    "african wildlife", "field guide", "nature b-roll",
]


class UniversalDownloaderError(Exception):
    """Base exception for universal downloader errors."""
    pass


class DurationFilteredError(UniversalDownloaderError):
    """Raised when video duration is outside the accepted range."""
    pass


class YouTubeBlockedError(UniversalDownloaderError):
    """YouTube refused access (anti-bot / sign-in wall). Callers must stop online sourcing, not retry."""
    pass


_BLOCK_MARKERS = ("confirm you", "not a bot", "sign in to confirm", "http error 429", "too many requests")


def _raise_if_blocked(exc: BaseException) -> None:
    msg = str(exc).lower()
    if any(m in msg for m in _BLOCK_MARKERS):
        raise YouTubeBlockedError(f"YouTube chặn truy cập (anti-bot/rate-limit): {str(exc)[:200]}") from exc

# ADR-020: flat search + download only the best few candidates (was: full probe of every result)
MAX_DOWNLOAD_ATTEMPTS = 3


@dataclass
class UniversalVideoInfo:
    """Metadata for a video downloaded via universal extractor."""

    video_id: str
    title: str
    downloaded_path: Path
    duration_sec: float
    extractor: str
    width: int = 0
    height: int = 0
    webpage_url: str = ""
    uploader: str = ""
    chapters: Optional[List[Dict[str, Any]]] = None
    categories: Optional[List[str]] = None
    description: str = ""


class UniversalDownloader:
    """
    Universal multi-platform downloader wrapping yt-dlp with duration constraints.
    """

    def __init__(self, config: Optional[AppConfig] = None):
        self.config = config or get_config()
        self.binary_manager = BinaryManager()

    def get_video_info(self, url: str, flat: Optional[bool] = None) -> Dict[str, Any]:
        """Probe video metadata without downloading stream.

        For search URLs (ytsearchN:) a *flat* listing is used by default (ADR-020): only the
        search page is requested instead of one watch-page request per result, which is far
        cheaper and avoids triggering YouTube's anti-bot wall.
        """
        if flat is None:
            flat = url.startswith("ytsearch")
        ydl_opts: Dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "ignoreerrors": not flat,
        }
        if flat:
            ydl_opts["extract_flat"] = "in_playlist"
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
                return info or {}
            except Exception as e:
                _raise_if_blocked(e)
                raise UniversalDownloaderError(f"Failed to probe URL {url}: {e}") from e

    def _verify_video_file(self, file_path: Path) -> bool:
        """
        Verify that a downloaded video file is non-empty, contains valid video streams
        with a determined pixel format, and can be read by FFmpeg without immediate EOF errors.
        """
        if not file_path.exists() or file_path.stat().st_size < 10000:
            return False

        try:
            ffprobe_info = self.binary_manager.check_binary("ffprobe")
            ffmpeg_info = self.binary_manager.check_binary("ffmpeg")

            if not ffprobe_info.is_available or not ffprobe_info.path:
                return file_path.stat().st_size > 10000

            # 1. Quick probe with ffprobe to check pix_fmt and streams
            cmd = [
                str(ffprobe_info.path),
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=codec_type,pix_fmt,width,height",
                "-of", "json",
                str(file_path),
            ]
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            if proc.returncode != 0:
                logger.warning("ffprobe verification returned code %s for %s", proc.returncode, file_path.name)
                return False

            data = json.loads(proc.stdout)
            streams = data.get("streams", [])
            if not streams:
                logger.warning("ffprobe found no video streams in %s", file_path.name)
                return False

            v_stream = streams[0]
            pix_fmt = v_stream.get("pix_fmt")
            if not pix_fmt or pix_fmt in ("unknown", "none"):
                logger.warning("Invalid/unknown pix_fmt '%s' in %s", pix_fmt, file_path.name)
                return False

            w = int(v_stream.get("width") or 0)
            h = int(v_stream.get("height") or 0)
            if w <= 0 or h <= 0:
                logger.warning("Invalid dimensions %sx%s in %s", w, h, file_path.name)
                return False

            # 2. Fast 0.1s decode test with ffmpeg if available to catch truncated/partial files
            if ffmpeg_info.is_available and ffmpeg_info.path:
                ff_cmd = [
                    str(ffmpeg_info.path),
                    "-v", "error",
                    "-i", str(file_path),
                    "-t", "0.1",
                    "-f", "null",
                    "-",
                ]
                ff_proc = subprocess.run(
                    ff_cmd,
                    capture_output=True,
                    text=True,
                    timeout=10,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                )
                if ff_proc.returncode != 0:
                    logger.warning(
                        "ffmpeg null decode test failed for %s (exit code %s): %s",
                        file_path.name, ff_proc.returncode, ff_proc.stderr
                    )
                    return False

            return True
        except Exception as exc:
            logger.warning("Video verification exception for %s: %s", file_path.name, exc)
            return False

    def _download_and_verify(
        self,
        target_url: str,
        video_id: str,
        dest_dir: Path,
    ) -> Path:
        """Download stream via yt-dlp with HD preference (>=720p/1080p) and verify file integrity.

        ADR-020: a previously downloaded, valid file is reused instead of re-downloading.
        """
        cached = dest_dir / f"universal_{video_id}.mp4"
        if cached.exists() and self._verify_video_file(cached):
            logger.info("Dùng lại footage đã tải trong cache: %s", cached.name)
            return cached

        outtmpl = str(dest_dir / f"universal_{video_id}.%(ext)s")
        bm = BinaryManager(self.config)
        ffmpeg_bin, _ = bm.find_binary("ffmpeg")

        ydl_opts = {
            "outtmpl": outtmpl,
            "format": (
                "bestvideo[height<=1080]+bestaudio/"
                "bestvideo+bestaudio/"
                "best[height>=720]/"
                "best"
            ),
            "quiet": True,
            "no_warnings": True,
            "merge_output_format": "mp4",
            "overwrites": True,
            "noplaylist": True,
        }
        if ffmpeg_bin:
            ydl_opts["ffmpeg_location"] = str(ffmpeg_bin)

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                ydl.download([target_url])
            except Exception as exc:
                _raise_if_blocked(exc)
                raise

        final_path = dest_dir / f"universal_{video_id}.mp4"
        if not final_path.exists():
            candidates = list(dest_dir.glob(f"universal_{video_id}.*"))
            if candidates:
                final_path = candidates[0]
            else:
                raise UniversalDownloaderError(f"Download completed but output file not found for: {target_url}")

        if not self._verify_video_file(final_path):
            final_path.unlink(missing_ok=True)
            raise UniversalDownloaderError(
                f"Tệp video tải về '{final_path.name}' bị lỗi/hỏng dữ liệu hoặc không đầy đủ (partial stream/corrupted). Đã xóa."
            )

        return final_path

    def download(
        self,
        url: str,
        output_dir: Optional[Path] = None,
        enforce_duration: bool = True,
        min_duration: float = 8.0,
        max_duration: float = 180.0,
        subject_anchor: Optional[str] = None,
        negative_terms: Optional[List[str]] = None,
        avoid_subjects: Optional[List[str]] = None,
        preferred_categories: Optional[List[str]] = None,
        discouraged_categories: Optional[List[str]] = None,
        trusted_channels: Optional[List[str]] = None,
        scene_terms: Optional[List[str]] = None,
        exclude_video_ids: Optional[List[str]] = None,
    ) -> UniversalVideoInfo:
        """
        Download a video from any supported platform to cache/raw_footage/.

        Args:
            url: Target URL.
            output_dir: Destination folder.
            enforce_duration: Whether to reject clips outside [min_duration, max_duration].
            min_duration: Minimum duration in seconds (default 8.0).
            max_duration: Maximum duration in seconds (default 180.0).
            subject_anchor: Primary entity/topic keyword (e.g. 'honey badger') for smart ranking.
            negative_terms: Blacklist terms to reject (news, cartoon, movie, reaction, etc.).
            avoid_subjects: Dynamically avoided subjects/entities for this specific scene.
            preferred_categories: YouTube categories to boost (+60), declared by Skill Niche.
            discouraged_categories: YouTube categories to reject (-800), declared by Skill Niche.
            trusted_channels: YouTube channels to boost (+60) for clean B-roll footage.
            scene_terms: Scene-specific visual terms (ADR-019). When provided, a candidate must
                mention at least one of them in title/description/tags, otherwise it is rejected.
            exclude_video_ids: Video IDs that must not be selected (reuse cap reached).

        Returns:
            UniversalVideoInfo with details and saved file Path.
        """
        dest_dir = output_dir or self.config.paths.cache_raw_footage_dir
        dest_dir.mkdir(parents=True, exist_ok=True)

        # 1. Probe duration if constraint is active
        info = self.get_video_info(url)
        entries = [e for e in info.get("entries", []) if isinstance(e, dict)]

        if entries:
            # Multi-result search (e.g. ytsearch5:)
            candidates_to_try: List[Dict[str, Any]] = []
            if enforce_duration:
                candidates_to_try = [
                    e for e in entries
                    if min_duration <= float(e.get("duration") or 0.0) <= max_duration
                ]
                if not candidates_to_try:
                    durations = [float(e.get("duration") or 0.0) for e in entries]
                    raise DurationFilteredError(
                        f"Không tìm thấy video nào trong {len(entries)} kết quả phù hợp khoảng thời lượng "
                        f"[{min_duration:.1f}s, {max_duration:.1f}s] (Các thời lượng: {durations})"
                    )
            else:
                candidates_to_try = [
                    e for e in entries
                    if float(e.get("duration") or 0.0) <= 300.0
                ] or entries

            # Reuse cap (ADR-019): never re-select a source video that already reached its usage limit
            if exclude_video_ids:
                excluded = {str(v) for v in exclude_video_ids}
                candidates_to_try = [e for e in candidates_to_try if str(e.get("id") or "") not in excluded]
                if not candidates_to_try:
                    raise UniversalDownloaderError(
                        f"Mọi kết quả cho '{url}' đều đã đạt giới hạn tái sử dụng footage."
                    )

            # Active negative terms (exclude terms that were explicitly requested in search query)
            query_lower = url.lower()
            active_negatives = [
                t.lower().strip() for t in DEFAULT_NEGATIVE_TERMS
                if t.lower().strip() and t.lower().strip() not in query_lower
            ]
            if negative_terms:
                active_negatives.extend([
                    t.lower().strip() for t in negative_terms
                    if t.strip() and t.lower().strip() not in query_lower
                ])
            if avoid_subjects:
                active_negatives.extend([
                    s.lower().strip() for s in avoid_subjects
                    if s.strip() and s.lower().strip() not in query_lower
                ])

            # Smart relevance scoring function
            def _calculate_score(c: Dict[str, Any]) -> float:
                score = 0.0
                title = str(c.get("title") or "").lower()
                uploader = str(c.get("uploader") or c.get("channel") or "").lower()
                desc = str(c.get("description") or "")[:400].lower()
                desc_full = str(c.get("description") or "")[:1500].lower()
                tags = [str(t).lower() for t in c.get("tags") or [] if t]
                combined_text = f"{title} {uploader} {desc} {' '.join(tags)}"

                # 1. Strict negative penalty (-1000) if matched in title or channel
                for neg in active_negatives:
                    if neg in title or neg in uploader:
                        return -1000.0

                # 2. Description/tags penalty (mild, do not discard legitimate documentaries that mention subscribe/interview in description)
                desc_ignore = ("subscribe", "subscriber", "subscribers", "like and subscribe", "news", "interview", "review", "vlog", "kids")
                for neg in active_negatives:
                    if neg not in desc_ignore and neg in combined_text:
                        score -= 80.0

                # 2. Subject anchor bonus (+150 full phrase in title, +30 head noun in title).
                # ADR-019: the anchor must be referenced in title/description/tags via the shared
                # anchor_matches() rule. Uploader-only or modifier-only ('spotted') matches are rejected.
                if subject_anchor:
                    anchor_clean = subject_anchor.lower().strip()
                    content_text = f"{title} {desc_full} {' '.join(tags)}"
                    if anchor_clean in title:
                        score += 150.0
                    elif anchor_clean in content_text:
                        score += 40.0
                    head = anchor_head(subject_anchor)
                    if head and anchor_matches(title, head):
                        score += 30.0
                    if anchor_clean in uploader:
                        score += 20.0

                    # Strict architectural contract: If candidate lacks the subject anchor, hard reject (-1000.0)
                    # Never accept an off-topic animal or entity just because of high resolution!
                    if not anchor_matches(content_text, subject_anchor):
                        return -1000.0

                # 2b. Scene-term gate (ADR-019): candidate must mention >=1 scene-specific visual term
                if scene_terms:
                    hits = matched_scene_terms(f"{title} {desc_full} {' '.join(tags)}", scene_terms)
                    if not hits:
                        return -900.0
                    score += min(len(hits), 4) * 15.0

                # 3. Query keywords bonus
                query_clean = url.replace("ytsearch8:", "").replace("ytsearch5:", "").replace('"', "").lower()
                query_words = [w for w in query_clean.split() if len(w) > 3]
                for qw in query_words:
                    if qw in title:
                        score += 20.0

                # 4. Global YouTube Category Alignment (Niche-declared via Skill)
                categories = [str(cat).lower() for cat in c.get("categories") or [] if cat]
                if discouraged_categories:
                    disc_cats = [dc.lower().strip() for dc in discouraged_categories if dc.strip()]
                    if any(any(d in cat for d in disc_cats) for cat in categories):
                        return -800.0

                if preferred_categories:
                    pref_cats = [pc.lower().strip() for pc in preferred_categories if pc.strip()]
                    if any(any(p in cat for p in pref_cats) for cat in categories):
                        score += 60.0

                # 5. Clean documentary channels bonus (+60)
                active_trusted = trusted_channels if trusted_channels is not None else TRUSTED_DOC_CHANNELS
                for ch in active_trusted:
                    ch_clean = ch.lower().strip()
                    if ch_clean and (ch_clean in uploader or ch_clean in title):
                        score += 60.0
                        break

                # 5. Dynamic Contextual Avoid Subjects guard (reject entities explicitly avoided for this scene)
                anchor_clean = (subject_anchor or "").lower().strip()
                if avoid_subjects:
                    for av in avoid_subjects:
                        av_clean = av.lower().strip()
                        if av_clean and av_clean in title:
                            if av_clean not in query_clean and (not anchor_clean or av_clean not in anchor_clean):
                                return -800.0

                # 6. Technical resolution and strict 16:9 widescreen aspect ratio
                h = int(c.get("height") or 0)
                w = int(c.get("width") or 0)
                # Reject poor low-res videos (< 480p, e.g. 360p)
                if 0 < h < 480:
                    return -800.0

                # Strict Aspect Ratio enforcement:
                # 16:9 widescreen is ~1.778. Any video with AR < 1.55 (4:3 = 1.33, 1:1 = 1.0, vertical = 0.56) is heavily penalized!
                if w > 0 and h > 0:
                    ar = w / float(h)
                    if ar < 1.0:
                        # Vertical video (9:16 Shorts/TikTok) -> HARD REJECT for landscape documentary
                        return -800.0
                    elif ar < 1.55:
                        # 4:3 or square video -> Severe penalty (-500.0) so widescreen 16:9 is always preferred
                        return -500.0
                    elif 1.65 <= ar <= 1.95:
                        # Clean 16:9 widescreen bonus
                        score += 30.0

                if 0 < h < 720:
                    score -= 50.0  # Mild penalty for 480p compared to HD
                elif h >= 1080 or w >= 1920:
                    score += 35.0
                elif h >= 720 or w >= 1280:
                    score += 20.0

                return score

            # Filter candidates: prioritize clean candidates (score >= 0)
            scored_candidates = [(c, _calculate_score(c)) for c in candidates_to_try]
            clean_candidates = [c for c, s in scored_candidates if s >= 0]
            if clean_candidates:
                clean_candidates.sort(key=_calculate_score, reverse=True)
                candidates_to_try = clean_candidates
            else:
                # If no clean candidate, only allow candidates without hard rejection (s > -200)
                semi_clean = [c for c, s in scored_candidates if s > -200]
                if semi_clean:
                    semi_clean.sort(key=_calculate_score, reverse=True)
                    candidates_to_try = semi_clean
                else:
                    logger.warning("Mọi video tìm kiếm đều dính từ khóa cấm/tiêu cực hoặc không chứa subject anchor '%s'.", subject_anchor)
                    raise UniversalDownloaderError(
                        f"Không tìm thấy video hợp lệ cho tìm kiếm '{url}' (Mọi kết quả đều bị loại bởi bộ lọc tiêu cực/subject anchor)"
                    )

            last_dl_err: Optional[Exception] = None
            for entry in candidates_to_try[:MAX_DOWNLOAD_ATTEMPTS]:
                try:
                    video_id = str(entry.get("id") or "asset")
                    title = str(entry.get("title") or video_id)
                    duration = float(entry.get("duration") or 0.0)
                    extractor = str(entry.get("extractor") or "youtube")
                    target_url = entry.get("webpage_url") or f"https://www.youtube.com/watch?v={video_id}"
                    width = int(entry.get("width") or 0)
                    height = int(entry.get("height") or 0)
                    webpage_url = str(entry.get("webpage_url") or target_url)
                    uploader = str(entry.get("uploader") or entry.get("channel") or "")

                    final_path = self._download_and_verify(target_url, video_id, dest_dir)
                    return UniversalVideoInfo(
                        video_id=video_id,
                        title=title,
                        downloaded_path=final_path,
                        duration_sec=duration,
                        extractor=extractor,
                        width=width,
                        height=height,
                        webpage_url=webpage_url,
                        uploader=uploader,
                        chapters=entry.get("chapters"),
                        categories=entry.get("categories"),
                        description=str(entry.get("description") or ""),
                    )
                except YouTubeBlockedError:
                    raise
                except Exception as exc:
                    logger.warning("Thử tải candidate %s thất bại: %s. Thử ứng viên tiếp theo...", entry.get("id"), exc)
                    last_dl_err = exc
                    continue

            raise UniversalDownloaderError(
                f"Đã thử {min(len(candidates_to_try), MAX_DOWNLOAD_ATTEMPTS)} ứng viên video cho '{url}' nhưng đều thất bại: {last_dl_err}"
            )
        else:
            # Single video / Direct URL
            duration = float(info.get("duration") or 0.0)
            video_id = str(info.get("id") or "asset")
            title = str(info.get("title") or video_id)
            extractor = str(info.get("extractor") or "generic")
            width = int(info.get("width") or 0)
            height = int(info.get("height") or 0)

            if enforce_duration and duration > 0.0:
                if not (min_duration <= duration <= max_duration):
                    raise DurationFilteredError(
                        f"Video duration {duration:.1f}s outside accepted range [{min_duration}s, {max_duration}s]"
                    )

            target_download_url = info.get("webpage_url") or url
            webpage_url = str(info.get("webpage_url") or (f"https://www.youtube.com/watch?v={video_id}" if "youtube" in extractor.lower() else url))
            uploader = str(info.get("uploader") or info.get("channel") or "")

            final_path = self._download_and_verify(target_download_url, video_id, dest_dir)
            return UniversalVideoInfo(
                video_id=video_id,
                title=title,
                downloaded_path=final_path,
                duration_sec=duration,
                extractor=extractor,
                width=width,
                height=height,
                webpage_url=webpage_url,
                uploader=uploader,
                chapters=info.get("chapters"),
                categories=info.get("categories"),
                description=str(info.get("description") or ""),
            )
