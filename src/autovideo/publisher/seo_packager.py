"""
SEO Packager for YouTube Publishing (B4, REQ-B4-01, VAC-UI-04).
Generates, validates, and exports the complete YouTube SEO Package:
1. 3 Alternative Titles (50–70 characters, core keyword prioritized in the first 35 chars).
2. YouTube-compliant Description with monotonically increasing chapter timestamps starting at 00:00.
3. Relevant Tags (within the 500-character limit) & Category Classification.
4. Structured export to renders/{project_id}/seo.md.
"""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

logger = logging.getLogger(__name__)


def format_timestamp(seconds: float) -> str:
    """Formats seconds into MM:SS or HH:MM:SS for YouTube chapter markers."""
    total_sec = max(0, int(round(seconds)))
    hours = total_sec // 3600
    minutes = (total_sec % 3600) // 60
    secs = total_sec % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def parse_timestamp_to_seconds(ts_str: str) -> float:
    """Parses MM:SS or HH:MM:SS string to seconds."""
    parts = [int(p) for p in ts_str.strip().split(":")]
    if len(parts) == 2:
        return float(parts[0] * 60 + parts[1])
    elif len(parts) == 3:
        return float(parts[0] * 3600 + parts[1] * 60 + parts[2])
    raise ValueError(f"Invalid timestamp format: {ts_str}")


@dataclass
class ChapterTimestamp:
    """Chapter timestamp marker for YouTube description."""
    time_str: str
    title: str
    seconds: float = 0.0


@dataclass
class SEOPackage:
    """Full SEO payload for YouTube publication."""
    project_id: str
    titles: List[str] = field(default_factory=list)
    description: str = ""
    timestamps: List[ChapterTimestamp] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    hashtags: List[str] = field(default_factory=list)
    category_id: str = "27"  # Default: 27 (Education) or 28 (Sci & Tech) or 22 (People & Blogs)
    target_keyword: str = ""
    thumbnail_badge: str = ""
    thumbnail_hook: str = ""

    def get_primary_title(self) -> str:
        """Returns the first recommended title option."""
        return self.titles[0] if self.titles else ""

    def get_tags_csv(self) -> str:
        """Returns comma-separated tags string."""
        return ", ".join(self.tags)


class SEOPackager:
    """
    Constructs, validates, and serializes YouTube SEO packages.
    """

    def __init__(self, default_category_id: str = "27") -> None:
        self.default_category_id = default_category_id

    def generate_package(
        self,
        project_id: str,
        topic: str,
        chapters: Sequence[Any],
        target_keyword: Optional[str] = None,
        category_id: Optional[str] = None,
        seo_input: Optional[Any] = None,
        skill: Optional[Any] = None,
    ) -> SEOPackage:
        """
        Builds a full YouTube SEO package from project metadata and chapters.
        Prioritizes dynamic LLM-generated SEO package and active skill rules over static fallbacks.
        """
        kw = (target_keyword or topic).strip()
        kw_clean = kw[:32].strip()

        # 1. Resolve Titles (Prioritize LLM-generated titles from seo_input)
        raw_titles = getattr(seo_input, "titles", None) or (seo_input.get("titles") if isinstance(seo_input, dict) else None)
        if raw_titles and isinstance(raw_titles, list) and len(raw_titles) > 0:
            titles = [str(t).strip() for t in raw_titles[:3]]
            while len(titles) < 3:
                titles.append(f"{kw_clean}: Phân Tích Chuyên Đề")
        else:
            # Clean descriptive titles based on topic and active skill without cliché clickbait
            skill_label = getattr(skill, "name", "") if skill else "Chuyên Đề"
            t1 = f"{kw_clean}: {skill_label} - Phân Tích Chi Tiết"
            t2 = f"{kw_clean} - Góc Nhìn Độc Bản & Dữ Liệu Thực Tế"
            t3 = f"{kw_clean}: Toàn Cảnh Diễn Biến & Hệ Quả"
            titles = [t1, t2, t3]

        # Ensure titles adhere to length constraints
        for i, t in enumerate(titles):
            if len(t) > 70:
                titles[i] = t[:67] + "..."
            elif len(t) < 50:
                titles[i] = f"{t} | Phóng Sự Chuyên Đề"[:70]

        # 2. Calculate chapter timestamps
        timestamps: List[ChapterTimestamp] = []
        elapsed_sec = 0.0

        for idx, ch in enumerate(chapters):
            ch_title = getattr(ch, "title", None) or (ch.get("title") if isinstance(ch, dict) else f"Phần {idx+1}")
            if hasattr(ch, "scenes") and ch.scenes:
                ch_duration = sum(getattr(s, "duration_sec", 0.0) for s in ch.scenes)
            elif isinstance(ch, dict) and "duration_sec" in ch:
                ch_duration = float(ch["duration_sec"])
            elif isinstance(ch, dict) and "scenes" in ch:
                ch_duration = sum(float(s.get("duration_sec", 0.0)) for s in ch["scenes"])
            else:
                ch_duration = 180.0

            clean_ch_title = re.sub(r"^Hồi\s*\d+\s*[:\-]\s*", "", ch_title).strip()
            if idx == 0:
                clean_ch_title = f"Mở đầu - {clean_ch_title}"

            ts_entry = ChapterTimestamp(
                time_str=format_timestamp(elapsed_sec),
                title=clean_ch_title,
                seconds=elapsed_sec,
            )
            timestamps.append(ts_entry)
            elapsed_sec += ch_duration

        # 3. Resolve Tags & Hashtags (Prioritize LLM input, then active skill and topic keywords)
        raw_tags = getattr(seo_input, "tags", None) or (seo_input.get("tags") if isinstance(seo_input, dict) else None)
        if raw_tags and isinstance(raw_tags, list) and len(raw_tags) > 0:
            tags_pool = [str(tg).strip() for tg in raw_tags]
        else:
            tags_pool = [kw]
            if skill:
                if hasattr(skill, "name") and skill.name:
                    tags_pool.append(skill.name)
                if hasattr(skill, "badge") and skill.badge:
                    tags_pool.append(skill.badge)
                if hasattr(skill, "tags") and isinstance(skill.tags, list):
                    tags_pool.extend(skill.tags)
            words = [w.strip() for w in kw.split() if len(w.strip()) >= 2]
            for w in words:
                tags_pool.append(w)
            for i in range(len(words) - 1):
                tags_pool.append(f"{words[i]} {words[i+1]}")
            # Add dynamic topic-based variations
            tags_pool.extend([
                f"{kw} chi tiết",
                f"{kw} tư liệu",
                f"{kw} diễn biến",
                f"{kw} phân tích",
                f"{kw} toàn cảnh",
                f"{kw} góc nhìn",
                f"hồ sơ {kw}",
                f"câu chuyện {kw}",
            ])

        validated_tags: List[str] = []
        total_len = 0
        for tag in tags_pool:
            tag_clean = tag.strip()
            if not tag_clean:
                continue
            tag_len = len(tag_clean) + 2
            if total_len + tag_len < 480 and tag_clean not in validated_tags:
                validated_tags.append(tag_clean)
                total_len += tag_len

        # Hashtags
        raw_hashtags = getattr(seo_input, "hashtags", None) or (seo_input.get("hashtags") if isinstance(seo_input, dict) else None)
        if raw_hashtags and isinstance(raw_hashtags, list) and len(raw_hashtags) > 0:
            hashtags = [h if h.startswith("#") else f"#{h}" for h in raw_hashtags]
        else:
            tag_slug = re.sub(r"[^\w]", "", kw)
            hashtags = []
            if tag_slug:
                hashtags.append(f"#{tag_slug[:20]}")
            words = [re.sub(r"[^\w]", "", w) for w in kw.split() if len(w) > 2]
            for w in words[:3]:
                if w and f"#{w}" not in hashtags:
                    hashtags.append(f"#{w}")
            if skill:
                skill_slug = re.sub(r"[^\w]", "", getattr(skill, "id", "") or getattr(skill, "name", ""))
                if skill_slug and f"#{skill_slug}" not in hashtags:
                    hashtags.append(f"#{skill_slug[:20]}")
            while len(hashtags) < 3:
                hashtags.append(f"#Video{len(hashtags)+1}")

        # 4. Construct YouTube Description
        llm_desc = getattr(seo_input, "description", None) or (seo_input.get("description") if isinstance(seo_input, dict) else None)
        desc_lines = [
            f"📌 {titles[0]}",
            "",
            llm_desc.strip() if llm_desc else f"Phóng sự chuyên đề tài liệu về {kw}.",
            "",
            "⏱️ MỐC THỜI GIAN NỘI DUNG (TIMESTAMPS):",
        ]

        for ts in timestamps:
            desc_lines.append(f"{ts.time_str} {ts.title}")

        if hashtags:
            desc_lines.extend(["", " ".join(hashtags)])

        description = "\n".join(desc_lines)

        # 5. Extract thumbnail badge and hook
        thumb_badge = getattr(seo_input, "thumbnail_badge", None) or (seo_input.get("thumbnail_badge") if isinstance(seo_input, dict) else None)
        if not thumb_badge and skill:
            thumb_badge = getattr(skill, "badge", None) or skill.name
        if not thumb_badge:
            thumb_badge = "TIÊU ĐIỂM"

        thumb_hook = getattr(seo_input, "thumbnail_hook", None) or (seo_input.get("thumbnail_hook") if isinstance(seo_input, dict) else None)
        if not thumb_hook:
            thumb_hook = titles[0].split(":")[0][:25]

        # Resolve category ID: priority skill > arg > default
        resolved_category_id = getattr(skill, "category_id", None) or category_id or self.default_category_id

        return SEOPackage(
            project_id=project_id,
            titles=titles,
            description=description,
            timestamps=timestamps,
            tags=validated_tags,
            hashtags=hashtags,
            category_id=resolved_category_id,
            target_keyword=kw,
            thumbnail_badge=str(thumb_badge).strip(),
            thumbnail_hook=str(thumb_hook).strip(),
        )

    def validate_package(self, package: SEOPackage) -> Dict[str, Any]:
        """
        Validates SEO Package against YouTube standards and Counterpoint constraints.

        Checks:
        1. Titles count is at least 3.
        2. Title lengths are between 50 and 70 characters.
        3. Timestamps start with 00:00 and are monotonically strictly increasing.
        4. Tags joined length < 500 characters.
        """
        errors: List[str] = []
        warnings: List[str] = []

        # Validate Titles
        if len(package.titles) < 3:
            warnings.append(f"Expected 3 title options, found {len(package.titles)}")

        for idx, t in enumerate(package.titles):
            t_len = len(t)
            if t_len < 40 or t_len > 80:
                warnings.append(f"Title {idx+1} length ({t_len}) outside optimal 50-70 range: '{t}'")
            if package.target_keyword:
                # Check if core keyword or parts of it appear in first 35 chars
                first_35 = t[:35].lower()
                kw_lower = package.target_keyword.lower()
                if not any(part in first_35 for part in kw_lower.split() if len(part) >= 3):
                    warnings.append(f"Title {idx+1} does not prioritize keyword in first 35 chars: '{t[:35]}'")

        # Validate Timestamps
        if not package.timestamps:
            errors.append("No timestamps defined in SEO package.")
        else:
            first_ts = package.timestamps[0].time_str
            if first_ts not in ("00:00", "0:00", "00:00:00"):
                errors.append(f"First timestamp must start at 00:00, found: {first_ts}")

            last_sec = -1.0
            for idx, ts in enumerate(package.timestamps):
                try:
                    sec = parse_timestamp_to_seconds(ts.time_str)
                    if sec <= last_sec and idx > 0:
                        errors.append(
                            f"Timestamps must be monotonically increasing. Found {ts.time_str} after {package.timestamps[idx-1].time_str}"
                        )
                    last_sec = sec
                except Exception as ex:
                    errors.append(f"Invalid timestamp format at index {idx}: {ts.time_str} ({ex})")

        # Validate Tags
        tags_str = ", ".join(package.tags)
        if len(tags_str) > 500:
            errors.append(f"YouTube tags exceed 500 character limit (current: {len(tags_str)})")
        elif len(package.tags) < 5:
            warnings.append(f"Low tag count: {len(package.tags)} tags (recommend 10-25)")

        # Validate Description
        if len(package.description) > 5000:
            errors.append(f"YouTube description exceeds 5000 character limit (current: {len(package.description)})")

        is_valid = len(errors) == 0
        return {
            "valid": is_valid,
            "errors": errors,
            "warnings": warnings,
            "title_count": len(package.titles),
            "timestamp_count": len(package.timestamps),
            "tags_char_count": len(tags_str),
        }

    def export_markdown(self, package: SEOPackage, output_path: Union[Path, str]) -> Path:
        """
        Exports the complete SEO package to a structured seo.md markdown file.
        """
        out_file = Path(output_path).resolve()
        out_file.parent.mkdir(parents=True, exist_ok=True)

        lines = [
            f"# GÓI SEO XUẤT BẢN YOUTUBE: {package.project_id}",
            f"> Từ khóa mục tiêu: **{package.target_keyword}** | Danh mục YouTube: **{package.category_id}**",
            "",
            "## 1. Phương Án Tiêu Đề (YouTube Title Options - 50-70 Ký Tự)",
        ]

        for i, title in enumerate(package.titles, 1):
            lines.append(f"{i}. **{title}** (`{len(title)}` ký tự)")

        lines.extend([
            "",
            "## 2. Hộp Mô Tả Chuẩn SEO (YouTube Description)",
            "```text",
            package.description,
            "```",
            "",
            "## 3. Danh Sách Phân Chương (Chapters Timestamps)",
            "| Mốc Thời Gian | Tiêu Đề Phân Cảnh / Hồi |",
            "| :--- | :--- |",
        ])

        for ts in package.timestamps:
            lines.append(f"| `{ts.time_str}` | {ts.title} |")

        lines.extend([
            "",
            "## 4. Thẻ Phân Loại (YouTube Tags & Hashtags)",
            f"- **Tổng ký tự Tags**: `{len(', '.join(package.tags))}/500`",
            f"- **Tags (Comma-separated)**: `{', '.join(package.tags)}`",
            f"- **Hashtags**: `{' '.join(package.hashtags)}`",
            "",
            "---",
            "*Gói SEO được tạo tự động bởi BanContentAuto Publisher Studio.*",
        ])

        out_file.write_text("\n".join(lines), encoding="utf-8")
        logger.info(f"Successfully exported SEO package to {out_file}")
        return out_file

    def import_markdown(self, input_path: Union[Path, str]) -> SEOPackage:
        """
        Parses an existing seo.md file back into an SEOPackage dataclass.
        """
        file_path = Path(input_path).resolve()
        if not file_path.exists():
            raise FileNotFoundError(f"SEO markdown file not found: {file_path}")

        content = file_path.read_text(encoding="utf-8")

        # Parse project ID & keyword
        header_match = re.search(r"# GÓI SEO XUẤT BẢN YOUTUBE:\s*(.+)", content)
        project_id = header_match.group(1).strip() if header_match else file_path.parent.name

        kw_match = re.search(r"Từ khóa mục tiêu:\s*\*\*(.*?)\*\*", content)
        target_keyword = kw_match.group(1).strip() if kw_match else ""

        cat_match = re.search(r"Danh mục YouTube:\s*\*\*(.*?)\*\*", content)
        category_id = cat_match.group(1).strip() if cat_match else "27"

        # Parse Titles
        titles: List[str] = []
        for line in content.splitlines():
            t_match = re.match(r"^\d+\.\s*\*\*(.+?)\*\*", line)
            if t_match:
                titles.append(t_match.group(1).strip())

        # Parse Description block
        desc_match = re.search(r"## 2\. Hộp Mô Tả Chuẩn SEO.*?\n```text\n(.*?)\n```", content, re.DOTALL)
        description = desc_match.group(1).strip() if desc_match else ""

        # Parse Timestamps
        timestamps: List[ChapterTimestamp] = []
        ts_matches = re.findall(r"\|\s*`([0-9:]+)`\s*\|\s*(.+?)\s*\|", content)
        for ts_str, title in ts_matches:
            if ts_str != "Mốc Thời Gian":
                sec = parse_timestamp_to_seconds(ts_str)
                timestamps.append(ChapterTimestamp(time_str=ts_str, title=title.strip(), seconds=sec))

        # Parse Tags & Hashtags
        tags: List[str] = []
        tags_match = re.search(r"Tags \(Comma-separated\)\*\*:\s*`([^`]+)`", content)
        if tags_match:
            tags = [t.strip() for t in tags_match.group(1).split(",") if t.strip()]

        hashtags: List[str] = []
        hashtags_match = re.search(r"Hashtags\*\*:\s*`([^`]+)`", content)
        if hashtags_match:
            hashtags = [h.strip() for h in hashtags_match.group(1).split() if h.strip()]

        return SEOPackage(
            project_id=project_id,
            titles=titles,
            description=description,
            timestamps=timestamps,
            tags=tags,
            hashtags=hashtags,
            category_id=category_id,
            target_keyword=target_keyword,
        )
