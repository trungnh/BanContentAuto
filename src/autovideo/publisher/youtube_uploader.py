"""
YouTube Uploader Adapter (B4, REQ-B4-02, VAC-UI-04).
Provides 1-Click Publishing integration with Google API Client / YouTube Data API v3.
Features:
- Resumable video upload with progress callback tracking.
- Custom thumbnail attachment (thumbnails.set).
- Metadata validation (Title <= 100 chars, Description <= 5000 chars, Tags <= 500 chars).
- API Quota estimation and limit tracking (1600 units per video insert).
- Robust Offline / Mock Mode for zero-cost operation, local testing, and automated test suites.
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)


@dataclass
class UploadStatus:
    """Status record of a YouTube video upload."""
    video_id: Optional[str] = None
    video_url: Optional[str] = None
    status: str = "initialized"  # initialized, uploading, completed, failed
    progress_percent: float = 0.0
    quota_used: int = 0
    error_message: Optional[str] = None
    thumbnail_uploaded: bool = False


class YouTubeUploadError(RuntimeError):
    """Raised when video publication to YouTube fails."""
    pass


class YouTubeUploader:
    """
    Adapter for publishing videos and thumbnails to YouTube via Data API v3.
    Operates in Mock Mode when credentials are not supplied or googleapiclient is unavailable.
    """

    # Quota cost constants defined by YouTube Data API v3
    VIDEO_INSERT_QUOTA_COST = 1600
    THUMBNAIL_SET_QUOTA_COST = 50
    DAILY_QUOTA_LIMIT = 10000

    def __init__(
        self,
        credentials_path: Optional[Union[Path, str]] = None,
        mock_mode: bool = True,
        initial_quota_used: int = 0,
    ) -> None:
        self.credentials_path = Path(credentials_path).resolve() if credentials_path else None
        self.mock_mode = mock_mode
        self.total_quota_consumed = initial_quota_used
        self._service: Optional[Any] = None

        if not self.mock_mode and self.credentials_path and self.credentials_path.exists():
            self._init_real_client()
        else:
            self.mock_mode = True
            logger.info("YouTubeUploader running in Mock Mode (offline / zero-cost).")

    def _init_real_client(self) -> None:
        """Attempts to initialize google-api-python-client."""
        try:
            from google.oauth2.credentials import Credentials  # type: ignore
            from googleapiclient.discovery import build  # type: ignore

            creds = Credentials.from_authorized_user_file(str(self.credentials_path))
            self._service = build("youtube", "v3", credentials=creds)
            self.mock_mode = False
            logger.info("Successfully connected to YouTube Data API v3.")
        except ImportError:
            logger.warning("google-api-python-client not installed. Falling back to Mock Mode.")
            self.mock_mode = True
        except Exception as ex:
            logger.warning(f"Failed to initialize YouTube client: {ex}. Falling back to Mock Mode.")
            self.mock_mode = True

    def check_quota(self, estimated_units: int = VIDEO_INSERT_QUOTA_COST) -> Dict[str, Any]:
        """
        Validates whether sufficient YouTube Data API quota is available for upload.
        """
        remaining = max(0, self.DAILY_QUOTA_LIMIT - self.total_quota_consumed)
        allowed = remaining >= estimated_units
        return {
            "allowed": allowed,
            "daily_limit": self.DAILY_QUOTA_LIMIT,
            "quota_consumed": self.total_quota_consumed,
            "quota_remaining": remaining,
            "required_units": estimated_units,
        }

    def validate_metadata(
        self,
        title: str,
        description: str,
        tags: Sequence[str],
    ) -> Tuple[bool, List[str]]:
        """
        Validates metadata constraints imposed by YouTube:
        - Title <= 100 characters.
        - Description <= 5000 characters.
        - Tags joined <= 500 characters.
        """
        errors: List[str] = []
        if not title.strip():
            errors.append("Title cannot be empty.")
        elif len(title) > 100:
            errors.append(f"Title exceeds 100 characters limit (current: {len(title)}).")

        if len(description) > 5000:
            errors.append(f"Description exceeds 5000 characters limit (current: {len(description)}).")

        tags_str = ",".join(tags)
        if len(tags_str) > 500:
            errors.append(f"Tags CSV string exceeds 500 characters limit (current: {len(tags_str)}).")

        return len(errors) == 0, errors

    def upload_video(
        self,
        video_path: Union[Path, str],
        title: str,
        description: str,
        tags: Sequence[str],
        category_id: str = "27",
        privacy_status: str = "private",  # private, unlisted, public
        thumbnail_path: Optional[Union[Path, str]] = None,
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> UploadStatus:
        """
        Uploads a video to YouTube with optional custom thumbnail and progress tracking.

        Args:
            video_path: Path to the target MP4 file.
            title: YouTube video title.
            description: YouTube description text.
            tags: List of search tags.
            category_id: Numerical category ID.
            privacy_status: 'private', 'unlisted', or 'public'.
            thumbnail_path: Optional thumbnail image to attach.
            progress_callback: Optional callback receiving (progress_percent, status_message).
        """
        v_path = Path(video_path).resolve()
        if not v_path.exists():
            raise FileNotFoundError(f"Video file not found: {v_path}")

        # Validate metadata
        is_valid, validation_errors = self.validate_metadata(title, description, tags)
        if not is_valid:
            raise YouTubeUploadError(f"Invalid YouTube metadata: {'; '.join(validation_errors)}")

        # Check API quota
        quota_check = self.check_quota(self.VIDEO_INSERT_QUOTA_COST)
        if not quota_check["allowed"]:
            raise YouTubeUploadError(
                f"Insufficient YouTube quota. Remaining: {quota_check['quota_remaining']}, required: {quota_check['required_units']}"
            )

        if self.mock_mode:
            return self._mock_upload(
                video_path=v_path,
                title=title,
                thumbnail_path=Path(thumbnail_path).resolve() if thumbnail_path else None,
                progress_callback=progress_callback,
            )
        else:
            return self._real_upload(
                video_path=v_path,
                title=title,
                description=description,
                tags=tags,
                category_id=category_id,
                privacy_status=privacy_status,
                thumbnail_path=Path(thumbnail_path).resolve() if thumbnail_path else None,
                progress_callback=progress_callback,
            )

    def _mock_upload(
        self,
        video_path: Path,
        title: str,
        thumbnail_path: Optional[Path],
        progress_callback: Optional[Callable[[float, str], None]],
    ) -> UploadStatus:
        """Simulates offline YouTube upload workflow for testing and local operation."""
        # Generate stable synthetic video ID from content and filename
        hash_digest = hashlib.sha256(f"{video_path.name}_{title}".encode("utf-8")).hexdigest()[:11]
        video_id = f"mock_{hash_digest}"

        stages = [
            (0.0, "Starting upload session..."),
            (25.0, "Uploading chunks (25%)..."),
            (50.0, "Uploading chunks (50%)..."),
            (75.0, "Uploading chunks (75%)..."),
            (100.0, "Upload completed! Processing video on YouTube..."),
        ]

        for pct, msg in stages:
            if progress_callback:
                progress_callback(pct, msg)

        self.total_quota_consumed += self.VIDEO_INSERT_QUOTA_COST

        thumbnail_success = False
        if thumbnail_path and thumbnail_path.exists():
            thumbnail_success = True
            self.total_quota_consumed += self.THUMBNAIL_SET_QUOTA_COST
            if progress_callback:
                progress_callback(100.0, f"Custom thumbnail attached from {thumbnail_path.name}")

        return UploadStatus(
            video_id=video_id,
            video_url=f"https://youtu.be/{video_id}",
            status="completed",
            progress_percent=100.0,
            quota_used=self.VIDEO_INSERT_QUOTA_COST + (self.THUMBNAIL_SET_QUOTA_COST if thumbnail_success else 0),
            thumbnail_uploaded=thumbnail_success,
        )

    def _real_upload(
        self,
        video_path: Path,
        title: str,
        description: str,
        tags: Sequence[str],
        category_id: str,
        privacy_status: str,
        thumbnail_path: Optional[Path],
        progress_callback: Optional[Callable[[float, str], None]],
    ) -> UploadStatus:
        """Executes actual upload using googleapiclient."""
        from googleapiclient.http import MediaFileUpload  # type: ignore

        body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": list(tags),
                "categoryId": category_id,
            },
            "status": {
                "privacyStatus": privacy_status,
                "selfDeclaredMadeForKids": False,
            },
        }

        media = MediaFileUpload(
            str(video_path),
            chunksize=1024 * 1024 * 4,  # 4MB chunks
            resumable=True,
            mimetype="video/mp4",
        )

        request = self._service.videos().insert(
            part=",".join(body.keys()),
            body=body,
            media_body=media,
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                pct = float(status.progress() * 100.0)
                if progress_callback:
                    progress_callback(pct, f"Uploading to YouTube: {pct:.1f}%")

        video_id = response.get("id")
        self.total_quota_consumed += self.VIDEO_INSERT_QUOTA_COST

        # Set thumbnail if provided
        thumb_success = False
        if thumbnail_path and thumbnail_path.exists() and video_id:
            thumb_success = self.set_thumbnail(video_id, thumbnail_path)

        return UploadStatus(
            video_id=video_id,
            video_url=f"https://youtu.be/{video_id}",
            status="completed",
            progress_percent=100.0,
            quota_used=self.VIDEO_INSERT_QUOTA_COST + (self.THUMBNAIL_SET_QUOTA_COST if thumb_success else 0),
            thumbnail_uploaded=thumb_success,
        )

    def set_thumbnail(self, video_id: str, thumbnail_path: Union[Path, str]) -> bool:
        """Sets custom thumbnail for an existing YouTube video."""
        thumb_p = Path(thumbnail_path).resolve()
        if not thumb_p.exists():
            raise FileNotFoundError(f"Thumbnail file not found: {thumb_p}")

        if self.mock_mode:
            self.total_quota_consumed += self.THUMBNAIL_SET_QUOTA_COST
            logger.info(f"Mock thumbnail set for video {video_id} using {thumb_p.name}")
            return True

        from googleapiclient.http import MediaFileUpload  # type: ignore
        media = MediaFileUpload(str(thumb_p), mimetype="image/jpeg")
        self._service.thumbnails().set(videoId=video_id, media_body=media).execute()
        self.total_quota_consumed += self.THUMBNAIL_SET_QUOTA_COST
        return True
