"""
Scene Editor (ADR-021, part A): dashboard operations on an already rendered project.

- list_alternatives(project, scene)  -> CLIP-ranked unused footage windows + preview strips (no LLM)
- apply_window(project, scene, video_id, start)  -> re-cut that scene, then rebuild the final video
- redo_scene(project, scene)          -> automatic re-pick (library + 1 LLM call), excluding current footage
- redo_flagged(project)               -> redo every scene flagged needs_review
- rerender(project)                   -> back up rendered scenes/parts/final, then run the pipeline again

Long operations run in a background thread; progress is exposed via job_status() and pipeline events.
"""

from __future__ import annotations

import base64
import logging
import os
import shutil
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)

RUNNING_STAGES = ("B1_SCRIPT", "B2_SOURCING_TTS", "B3_RENDER", "B4_PACKAGING", "QUEUED")


class SceneEditError(RuntimeError):
    pass


class SceneEditor:
    def __init__(self, coordinator: Any) -> None:
        self.coord = coordinator
        self.config = coordinator.config
        self._lock = threading.Lock()
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._libs: Dict[str, Tuple[Any, Any, Any]] = {}  # anchor -> (library, matcher, judge)

    # ================================================================ helpers
    def _project(self, project_id: str) -> Any:
        p = self.coord.projects.get(project_id)
        if p is None:
            raise SceneEditError(f"Không tìm thấy dự án {project_id}")
        return p

    def _assert_editable(self, project_id: str) -> Any:
        p = self._project(project_id)
        stage = getattr(p.stage, "value", str(p.stage))
        if self.coord._running_project_id == project_id and stage in RUNNING_STAGES:
            raise SceneEditError("Dự án đang chạy pipeline, hãy đợi hoàn tất rồi chỉnh sửa scene.")
        job = self._jobs.get(project_id)
        if job and job.get("state") == "running":
            raise SceneEditError(f"Đang có thao tác khác chạy: {job.get('message')}")
        if not p.completed_scenes:
            raise SceneEditError("Dự án chưa có scene nào để chỉnh sửa.")
        return p

    def _scene_ctx(self, project: Any, scene_id: str) -> Tuple[int, Any, Any]:
        from autovideo.script.pipeline import Screenplay
        sp = Screenplay.model_validate(project.screenplay)
        scenes = sp.all_scenes
        for idx, sc in enumerate(scenes, start=1):
            if sc.scene_id == scene_id:
                rec = next((r for r in project.completed_scenes if r.scene_id == scene_id), None)
                if rec is None:
                    raise SceneEditError(f"Scene {scene_id} chưa được render.")
                return idx, sc, rec
        raise SceneEditError(f"Không có scene {scene_id} trong kịch bản.")

    def _anchor(self, project: Any) -> str:
        return self.coord._extract_subject_anchor(project.topic, project.skill_id) or ""

    def _library(self, project: Any) -> Tuple[Any, Any, Any]:
        anchor = self._anchor(project)
        if anchor in self._libs:
            return self._libs[anchor]
        from autovideo.core.settings import SettingsManager
        from autovideo.production.semantic_judge import SemanticFootageJudge
        settings = SettingsManager(config=self.config).load_settings()
        lib, matcher = self.coord._prepare_footage_library(
            project.project_id, anchor, max(1, int(getattr(settings, "footage_max_reuse", 2))), enabled=True,
            quiet=True,
        )
        if matcher is None:
            raise SceneEditError("CLIP chưa được cài. Vào Cài đặt → Binaries để tải CLIP.")
        judge = SemanticFootageJudge.from_settings(settings)
        conf_file = lib.index_dir / "confusers.json"
        try:
            import json
            conf = json.loads(conf_file.read_text(encoding="utf-8")).get(anchor.lower(), []) if conf_file.exists() else []
            matcher.set_confusers(conf)
        except Exception:
            pass
        self._libs[anchor] = (lib, matcher, judge)
        return self._libs[anchor]

    def _used_by_others(self, project: Any, scene_id: str) -> Tuple[Dict[str, List[Tuple[float, float]]], Dict[str, int]]:
        iv: Dict[str, List[Tuple[float, float]]] = {}
        ct: Dict[str, int] = {}
        for r in project.completed_scenes:
            if r.scene_id != scene_id:
                self.coord._track_footage_usage(r.metadata or {}, ct, iv)
        return iv, ct

    @staticmethod
    def _strip(path: Path, start: float, duration: float, ffmpeg_bin: Optional[Path]) -> Optional[str]:
        from autovideo.production.visual_inspector import VisualQualityInspector
        frames = []
        for r in (0.15, 0.5, 0.85):
            f = VisualQualityInspector._extract_frame(path, start + duration * r, ffmpeg_bin=ffmpeg_bin)
            frames.append(cv2.resize(f, (192, 108)) if f is not None else np.zeros((108, 192, 3), np.uint8))
        ok, buf = cv2.imencode(".jpg", np.hstack(frames), [int(cv2.IMWRITE_JPEG_QUALITY), 78])
        return base64.b64encode(buf.tobytes()).decode("ascii") if ok else None

    def _ffmpeg(self) -> Optional[Path]:
        from autovideo.core.binary_manager import BinaryManager
        ff, _ = BinaryManager(self.config).find_binary("ffmpeg")
        return ff

    def _emit(self, project_id: str, message: str, progress: Optional[float] = None, **details: Any) -> None:
        job = self._jobs.setdefault(project_id, {})
        job.update({"message": message, "updated_at": time.time()})
        if progress is not None:
            job["progress"] = progress
        try:
            p = self._project(project_id)
            self.coord.emit_event(project_id=project_id, stage=p.stage, progress=p.progress,
                                  message=message, details={"scene_editor": True, **details})
        except Exception:
            logger.info("[scene-editor %s] %s", project_id, message)

    # ============================================================ public API
    def job_status(self, project_id: str) -> Dict[str, Any]:
        return dict(self._jobs.get(project_id) or {"state": "idle"})

    def list_alternatives(self, project_id: str, scene_id: str, k: int = 6) -> Dict[str, Any]:
        project = self._project(project_id)
        idx, scene, rec = self._scene_ctx(project, scene_id)
        lib, matcher, _judge = self._library(project)
        from autovideo.footage.matcher import SceneQuery
        iv, ct = self._used_by_others(project, scene_id)
        meta = rec.metadata or {}
        cur_vid = str(meta.get("video_id") or "")
        cur_start = float(meta.get("start_offset_sec") or 0.0)
        rw = meta.get("visual_prompt_rewritten") or ""
        texts = [rw or getattr(scene, "visual_prompt", "")] + list(getattr(scene.keywords, "en", None) or [])
        cands = matcher.top_windows(SceneQuery(scene_id, float(rec.duration_sec), texts), iv, ct,
                                    top_k=k + 2, per_video=2, avoid_embeddings=matcher.used_embeddings(iv))
        ff = self._ffmpeg()
        out = []
        for c in cands:
            if c.video_id == cur_vid and abs(c.start - cur_start) < 1.0:
                continue
            vi = lib.videos[c.video_id]
            out.append({
                "video_id": c.video_id, "start": c.start, "end": c.end, "title": vi.entry.title,
                "clip_score": round(c.total, 4), "subject_score": round(c.subject_score, 4),
                "preview_jpg_b64": self._strip(vi.entry.path, c.start, float(rec.duration_sec), ff),
            })
            if len(out) >= k:
                break
        current = None
        raw = meta.get("raw_asset_path")
        if raw and Path(raw).exists():
            current = {"video_id": cur_vid, "start": cur_start, "title": meta.get("title") or "",
                       "preview_jpg_b64": self._strip(Path(raw), cur_start, float(rec.duration_sec), ff)}
        return {"scene_id": scene_id, "text": rec.text, "current": current, "alternatives": out}

    # ------------------------------------------------------------- jobs
    def _run_job(self, project_id: str, label: str, fn) -> Dict[str, Any]:
        with self._lock:
            self._assert_editable(project_id)
            self._jobs[project_id] = {"state": "running", "label": label, "message": label, "progress": 0.0,
                                      "started_at": time.time(), "result": None, "error": None}

        def _target() -> None:
            try:
                result = fn()
                self._jobs[project_id].update({"state": "done", "result": result, "progress": 100.0})
                self._emit(project_id, f"✅ {label}: hoàn tất")
            except Exception as exc:
                logger.exception("Scene editor job failed")
                self._jobs[project_id].update({"state": "error", "error": str(exc)})
                self._emit(project_id, f"❌ {label}: {exc}")

        threading.Thread(target=_target, name=f"scene-editor-{project_id}", daemon=True).start()
        return self.job_status(project_id)

    def apply_window(self, project_id: str, scene_id: str, video_id: str, start: float) -> Dict[str, Any]:
        def _do() -> Dict[str, Any]:
            project = self._project(project_id)
            lib, matcher, _ = self._library(project)
            if video_id not in lib.videos:
                raise SceneEditError(f"Video {video_id} không có trong thư viện footage")
            self._recut(project, scene_id, video_id, float(start),
                        semantic={"verdict": "user_selected", "method": "manual"}, reasons=[])
            self._rebuild_final(project)
            return {"scene_id": scene_id, "video_id": video_id, "start": start}
        return self._run_job(project_id, f"Đổi footage {scene_id}", _do)

    def redo_scene(self, project_id: str, scene_id: str) -> Dict[str, Any]:
        def _do() -> Dict[str, Any]:
            project = self._project(project_id)
            self._ensure_rewrites(project, [scene_id])
            res = self._auto_repick(project, scene_id)
            if not res.get("kept"):
                self._rebuild_final(project)
            else:
                self._emit(project_id, f"{scene_id}: {res.get('reason')}")
            return res
        return self._run_job(project_id, f"Làm lại {scene_id}", _do)

    def redo_flagged(self, project_id: str, force: bool = False) -> Dict[str, Any]:
        project = self._project(project_id)
        flagged = [r for r in project.completed_scenes if (r.metadata or {}).get("needs_review")]
        if not flagged:
            raise SceneEditError("Không có scene nào đang bị gắn cờ cần kiểm tra.")
        # Scenes the AI already tried against the SAME library state would just repeat the same result.
        fp = self._library_fingerprint(project)
        todo = [r.scene_id for r in flagged
                if force or not self._auto_exhausted(r, fp)]
        if not todo:
            raise SceneEditError(
                f"{len(flagged)} scene này AI đã thử cả thư viện footage lẫn tìm video mới trên YouTube nhưng không có "
                "đoạn nào tốt hơn, nên bấm lại cũng sẽ cho kết quả giống hệt. Hãy mở từng scene và bấm 'Chọn footage khác' "
                "để chọn tay, hoặc 'Chấp nhận' nếu thấy footage hiện tại đã ổn."
            )
        flagged_ids = todo

        def _do() -> Dict[str, Any]:
            p = self._project(project_id)
            self._ensure_rewrites(p, flagged_ids)
            online_state: Dict[str, Any] = {"blocked": False}
            results = []
            for n, sid in enumerate(flagged_ids, start=1):
                self._emit(project_id, f"Làm lại scene cần kiểm tra {n}/{len(flagged_ids)}: {sid}", 100.0 * (n - 1) / len(flagged_ids))
                try:
                    results.append(self._auto_repick(p, sid, online_state))
                except Exception as exc:
                    results.append({"scene_id": sid, "error": str(exc)})
            if any(not r.get("kept") and not r.get("error") for r in results):
                self._rebuild_final(p)
            changed = sum(1 for r in results if not r.get("kept") and not r.get("error"))
            still = sum(1 for r in p.completed_scenes if (r.metadata or {}).get("needs_review"))
            added = sum(len((r.get("online") or {}).get("added") or []) for r in results)
            return {"scenes": results, "changed": changed, "kept": len(results) - changed,
                    "skipped_exhausted": len(flagged) - len(flagged_ids), "still_flagged": still,
                    "online_added": added, "youtube_blocked": online_state["blocked"]}
        return self._run_job(project_id, f"Làm lại {len(flagged_ids)} scene cần kiểm tra", _do)

    def accept_scene(self, project_id: str, scene_id: str) -> Dict[str, Any]:
        """User confirms the current footage is acceptable -> clear the review flag (no re-render needed)."""
        project = self._assert_editable(project_id)
        _, _, rec = self._scene_ctx(project, scene_id)
        meta = dict(rec.metadata or {})
        meta["review_accepted"] = {"at": time.strftime("%Y-%m-%d %H:%M:%S"),
                                   "previous_reasons": list(meta.get("review_reasons") or [])}
        meta["needs_review"] = False
        meta["review_reasons"] = []
        rec.metadata = meta
        self.coord._save_project_state(project)
        still = sum(1 for r in project.completed_scenes if (r.metadata or {}).get("needs_review"))
        self._emit(project_id, f"✔ Đã chấp nhận footage của {scene_id} (còn {still} scene cần kiểm tra)")
        return {"scene_id": scene_id, "accepted": True, "still_flagged": still}

    # ------------------------------------------------------- attempt memory
    def _library_fingerprint(self, project: Any) -> str:
        """Changes whenever the usable footage library changes (new/removed/flagged videos)."""
        try:
            _, matcher, _ = self._library(project)
            vids = sorted(v.entry.video_id for v in matcher.eligible_videos())
            import hashlib
            return f"{len(vids)}:" + hashlib.md5(",".join(vids).encode()).hexdigest()[:10]
        except Exception:
            return "unknown"

    @staticmethod
    def _auto_exhausted(rec: Any, fingerprint: str) -> bool:
        """True only when BOTH the library (same fingerprint) and an online search were already tried."""
        info = (rec.metadata or {}).get("auto_redo") or {}
        online_done = bool((info.get("online") or {}).get("tried"))
        return (info.get("result") == "kept" and info.get("fingerprint") == fingerprint
                and fingerprint != "unknown" and online_done)

    def _remember_attempt(self, project: Any, scene_id: str, result: str, reason: str,
                          online: Optional[Dict[str, Any]] = None) -> None:
        rec = next((r for r in project.completed_scenes if r.scene_id == scene_id), None)
        if rec is None:
            return
        rec.metadata = {**(rec.metadata or {}), "auto_redo": {
            "at": time.strftime("%Y-%m-%d %H:%M:%S"), "result": result, "reason": reason,
            "fingerprint": self._library_fingerprint(project),
            "online": online or {"tried": False},
        }}
        self.coord._save_project_state(project)

    def rerender(self, project_id: str) -> Dict[str, Any]:
        project = self._assert_editable(project_id)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        bk = self.config.paths.cache_dir / "backups" / f"_backup_{project_id}_{stamp}"
        (bk / "temp_scenes").mkdir(parents=True, exist_ok=True)
        (bk / "render").mkdir(parents=True, exist_ok=True)
        temp_dir = self.config.paths.cache_temp_scenes_dir / project_id
        render_dir = self.config.paths.get_project_render_dir(project_id)
        moved = 0
        if temp_dir.exists():
            for f in temp_dir.iterdir():
                shutil.move(str(f), str(bk / "temp_scenes" / f.name))
                moved += 1
        for name in ("parts", "state.json", f"{project_id}_final.mp4"):
            src = render_dir / name
            if src.exists():
                shutil.move(str(src), str(bk / "render" / name))
        for name in ("project_state.json", "screenplay.json"):
            src = render_dir / name
            if src.exists():
                shutil.copy2(str(src), str(bk / "render" / name))
        res = self.coord.enqueue_project(project_id=project_id, resume=True)
        return {"backup_dir": str(bk), "moved_scene_files": moved, "pipeline": res.get("status") if isinstance(res, dict) else res}

    # ------------------------------------------------------------ internals
    @staticmethod
    def _prev_score(rec: Any) -> Optional[float]:
        sem = (rec.metadata or {}).get("semantic_check") or {}
        if sem.get("verdict") in ("user_selected",):
            return 10.0  # never auto-replace a footage the user picked by hand
        try:
            return float(sem.get("score")) if sem.get("method") in ("llm_choose_best", None) and sem.get("score") is not None else None
        except (TypeError, ValueError):
            return None

    def _ensure_rewrites(self, project: Any, scene_ids: List[str]) -> None:
        """ADR-021 B4 for already-rendered scenes: ONE batched call rewrites shots that have no rewrite yet."""
        lib, matcher, judge = self._library(project)
        todo = []
        for sid in scene_ids:
            _, scene, rec = self._scene_ctx(project, sid)
            if not (rec.metadata or {}).get("visual_prompt_rewritten"):
                todo.append({"scene_id": sid, "narration": rec.text, "visual_prompt": getattr(scene, "visual_prompt", "")})
        if not todo or not judge.active:
            return
        titles = sorted({vi.entry.title for vi in matcher.eligible_videos() if vi.entry.title})
        rewrites = judge.rewrite_visual_prompts(todo, titles, self._anchor(project))
        for sid, rw in rewrites.items():
            rec = next((r for r in project.completed_scenes if r.scene_id == sid), None)
            if rec is not None:
                rec.metadata = {**(rec.metadata or {}), "visual_prompt_rewritten": rw["visual_prompt"],
                                "keywords_rewritten": rw.get("keywords", [])}
        if rewrites:
            self.coord._save_project_state(project)
            self._emit(project.project_id, f"Đã viết lại mô tả shot theo kho footage cho {len(rewrites)} scene")

    def _library_pick(self, project: Any, scene_id: str) -> Tuple[Optional[Dict[str, Any]], bool]:
        """Best library window for the scene (excluding its current footage). Returns (pick, passed_threshold)."""
        from autovideo.footage.scene_picker import pick_library_window
        idx, scene, rec = self._scene_ctx(project, scene_id)
        lib, matcher, judge = self._library(project)
        iv, ct = self._used_by_others(project, scene_id)
        meta = rec.metadata or {}
        excl = []
        if meta.get("video_id"):
            s0 = float(meta.get("start_offset_sec") or 0.0)
            excl.append((str(meta["video_id"]), s0, s0 + float(rec.duration_sec)))
        rw = meta.get("visual_prompt_rewritten") or ""
        kws = list(meta.get("keywords_rewritten") or []) + list(getattr(scene.keywords, "en", None) or [])
        acc, fb = pick_library_window(
            lib=lib, matcher=matcher, judge=judge, scene_id=scene_id, duration=float(rec.duration_sec),
            narration=rec.text, visual_prompt=rw or getattr(scene, "visual_prompt", ""),
            en_keywords=kws, subject_anchor=self._anchor(project),
            used_intervals=iv, used_counts=ct, ffmpeg_bin=self._ffmpeg(), exclude_windows=excl,
        )
        if acc is not None and (acc.get("semantic") or {}).get("verdict") == "unavailable":
            # The vision judge did not answer (timeout/error): an unverified CLIP guess must NOT count as a pass.
            return {**acc, "judge_unavailable": True}, False
        return (acc or fb), acc is not None

    def _online_queries(self, project: Any, scene_id: str, max_queries: int = 3) -> List[str]:
        """Search phrases for new footage: rewritten shot keywords first, then the script's EN keywords."""
        _, scene, rec = self._scene_ctx(project, scene_id)
        meta = rec.metadata or {}
        anchor = self._anchor(project)
        raw = list(meta.get("keywords_rewritten") or []) + list(getattr(scene.keywords, "en", None) or [])
        out: List[str] = []
        for kw in raw:
            q = self.coord._build_natural_query(str(kw), anchor)
            if q and q not in out:
                out.append(q)
            if len(out) >= max_queries:
                break
        return out

    def _online_allowed(self) -> bool:
        try:
            from autovideo.core.settings import SettingsManager
            return bool(getattr(SettingsManager(config=self.config).load_settings(), "footage_online_augment", True))
        except Exception:
            return True

    def _auto_repick(self, project: Any, scene_id: str, online_state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        ADR-022: library first; if nothing passes, search ONLINE for new footage, add it to the library and
        pick again; finally keep-if-better. Each scene ends with an 'auto_redo' memory so repeated clicks
        never loop on the same result.
        """
        from autovideo.footage.online_augment import search_and_add
        online_state = online_state if online_state is not None else {"blocked": False}
        _, _, rec = self._scene_ctx(project, scene_id)
        lib, matcher, _ = self._library(project)
        prev = self._prev_score(rec)
        info = (rec.metadata or {}).get("auto_redo") or {}
        fp = self._library_fingerprint(project)
        library_exhausted = info.get("result") == "kept" and info.get("fingerprint") == fp

        best: Optional[Dict[str, Any]] = None
        best_passed = False
        if not library_exhausted:
            best, best_passed = self._library_pick(project, scene_id)
            if best is not None and best.get("judge_unavailable"):
                reason = ("AI chấm hình (9Router) không phản hồi/timeout nên chưa thể xác minh footage mới — "
                          "giữ nguyên footage hiện tại, hãy bấm làm lại sau ít phút.")
                rec.metadata = {**(rec.metadata or {}), "auto_redo": {
                    "at": time.strftime("%Y-%m-%d %H:%M:%S"), "result": "judge_unavailable", "reason": reason,
                    "fingerprint": fp, "online": {"tried": False}}}
                self.coord._save_project_state(project)
                return {"scene_id": scene_id, "kept": True, "score": prev, "reason": reason, "judge_unavailable": True}

        online: Dict[str, Any] = {"tried": False}
        if not best_passed and self._online_allowed() and not online_state.get("blocked"):
            queries = self._online_queries(project, scene_id)
            self._emit(project.project_id, f"{scene_id}: thư viện không có đoạn đạt — đang tìm footage mới trên YouTube...")
            aug = search_and_add(lib, queries, self._anchor(project), confusers=getattr(matcher, "confusers", []),
                                 max_new=3, progress=lambda m: self._emit(project.project_id, f"{scene_id}: {m}"))
            online = {"tried": not aug.blocked, **aug.to_dict()}
            if aug.blocked:
                online_state["blocked"] = True
                self._emit(project.project_id, "⚠ YouTube đang chặn truy cập — tạm dừng tìm footage online")
            if aug.added:
                pick2, passed2 = self._library_pick(project, scene_id)
                if pick2 is not None and pick2.get("judge_unavailable"):
                    pick2, passed2 = None, False   # unverified -> never replace on a CLIP guess
                s_best = float((best or {}).get("semantic", {}).get("score") or 0.0)
                s2 = float((pick2 or {}).get("semantic", {}).get("score") or 0.0)
                if pick2 is not None and (passed2 or best is None or s2 > s_best):
                    best, best_passed = pick2, passed2

        new_score = float((best or {}).get("semantic", {}).get("score") or 0.0)
        improves = best is not None and (best_passed or prev is None or new_score > prev)
        online_note = ""
        if online.get("tried"):
            online_note = (f" Đã tìm online và thêm {len(online['added'])} video mới vào thư viện."
                           if online.get("added") else " Đã tìm online nhưng không có video mới phù hợp.")
        elif online.get("blocked"):
            online_note = " YouTube đang chặn nên chưa tìm online được (sẽ thử lại lần sau)."

        if not improves:
            reason = ("Không có đoạn footage nào tốt hơn footage hiện tại"
                      + (f" ({prev:.0f}/10)" if prev is not None else "") + "." + online_note + " Giữ nguyên.")
            self._remember_attempt(project, scene_id, "kept", reason, online=online)
            return {"scene_id": scene_id, "kept": True, "score": prev, "reason": reason, "online": online}

        reasons = [] if best_passed else [f"semantic_below_threshold(score={best['semantic'].get('score')})"]
        sem = dict(best["semantic"])
        sem["library"] = best.get("library")
        lib_info = best.get("library") or {}
        self._recut(project, scene_id, lib_info["video_id"], float(best["offset"]), semantic=sem, reasons=reasons)
        if reasons:
            self._remember_attempt(project, scene_id, "kept",
                                   f"Đã thay bằng đoạn tốt hơn ({new_score:.0f}/10) nhưng vẫn dưới ngưỡng.{online_note} "
                                   "Nên xem lại bằng tay.", online=online)
        return {"scene_id": scene_id, "video_id": lib_info["video_id"], "start": best["offset"],
                "verdict": sem.get("verdict"), "score": sem.get("score"), "online": online}

    def _recut(self, project: Any, scene_id: str, video_id: str, start: float,
               semantic: Dict[str, Any], reasons: List[str]) -> None:
        from autovideo.coordinator import format_time_code
        from autovideo.footage.matcher import WindowCandidate
        from autovideo.footage.scene_picker import library_sourced_asset
        idx, scene, rec = self._scene_ctx(project, scene_id)
        lib, matcher, _ = self._library(project)
        vi = lib.videos[video_id]
        dur = float(rec.duration_sec)
        if start + dur > vi.duration_sec + 0.05:
            start = max(0.0, vi.duration_sec - dur)
        self._emit(project.project_id, f"Đang cắt lại {scene_id} từ '{vi.entry.title[:50]}' @ {format_time_code(start)}")

        temp_dir = self.config.paths.cache_temp_scenes_dir / project.project_id
        temp_dir.mkdir(parents=True, exist_ok=True)
        final_path = temp_dir / f"scene_{idx:03d}.mp4"
        tmp_path = temp_dir / f"scene_{idx:03d}.edit.mp4"
        mux = self.coord.scene_muxer.assemble_scene(
            project_id=project.project_id, scene_idx=idx, media_path=vi.entry.path,
            voiceover_audio_path=rec.audio_path, target_duration_sec=dur, start_offset_sec=start,
            output_path=tmp_path,
        )
        os.replace(str(mux.output_path), str(final_path))

        sourced = library_sourced_asset(lib, WindowCandidate(video_id, start, start + dur, 0, 0, 0, 0), scene_id,
                                        self._anchor(project))
        meta = dict(sourced.metadata)
        url = meta.get("webpage_url") or ""
        rec.video_path = str(final_path)
        rec.source_info = {
            "vault": "library", "platform": "YouTube", "url": url,
            "url_with_timestamp": f"{url}{'&' if '?' in url else '?'}t={int(start)}s" if url else "",
            "video_id": video_id, "start_offset_sec": start, "end_offset_sec": start + mux.duration_sec,
            "cut_from": format_time_code(start), "cut_to": format_time_code(start + mux.duration_sec),
            "cut_duration": round(mux.duration_sec),
            "cut_summary": f"{round(mux.duration_sec)}s cắt từ {format_time_code(start)} - {format_time_code(start + mux.duration_sec)}",
            "title": meta.get("title") or "", "uploader": meta.get("uploader") or "",
            "raw_filename": vi.entry.path.name, "query": meta.get("effective_query") or "",
        }
        old = rec.metadata or {}
        rec.metadata = {
            **meta,
            "raw_asset_path": str(vi.entry.path.resolve()),
            "start_offset_sec": start,
            "duration_sec": mux.duration_sec,
            "scene_terms": old.get("scene_terms"),
            "visual_prompt_rewritten": old.get("visual_prompt_rewritten"),
            "keywords_rewritten": old.get("keywords_rewritten"),
            "semantic_check": semantic,
            "needs_review": bool(reasons),
            "review_reasons": reasons,
            "edited": {"at": time.strftime("%Y-%m-%d %H:%M:%S"), "method": semantic.get("method"),
                       "previous": {"video_id": old.get("video_id"), "start": old.get("start_offset_sec")}},
        }
        self.coord._save_project_state(project)

    def _rebuild_final(self, project: Any) -> Path:
        """Re-concatenate all scene files into chapter parts + final video (no re-encode of other scenes)."""
        from autovideo.production.chapter_builder import ProductionPipeline, SceneAssets
        from autovideo.script.pipeline import Screenplay
        self._emit(project.project_id, "Đang ghép lại video cuối từ các scene...")
        sp = Screenplay.model_validate(project.screenplay)
        recs = {r.scene_id: r for r in project.completed_scenes}
        assets = {}
        for sc in sp.all_scenes:
            r = recs.get(sc.scene_id)
            if r is None or not r.video_path or not Path(r.video_path).exists():
                raise SceneEditError(f"Thiếu file scene {sc.scene_id}, không ghép được video cuối")
            assets[sc.scene_id] = SceneAssets(media_path=Path(r.video_path),
                                              audio_path=Path(r.audio_path) if r.audio_path else None,
                                              is_preassembled=True)
        pp = ProductionPipeline(config=self.config, chapter_builder=self.coord.chapter_builder,
                                concat_demuxer=self.coord.concat_demuxer, rolling_buffer=self.coord.rolling_buffer,
                                binary_manager=self.coord.binary_manager)
        out = self.config.paths.get_project_render_dir(project.project_id) / f"{project.project_id}_final.mp4"
        res = pp.run(project_id=project.project_id, screenplay=sp, asset_resolver=assets,
                     output_video_path=out, resume=False)
        project.final_video_path = str(res.final_video_path)
        self.coord._save_project_state(project)
        self._emit(project.project_id, f"Đã ghép lại video cuối ({res.total_duration_sec:.1f}s)")
        return res.final_video_path
