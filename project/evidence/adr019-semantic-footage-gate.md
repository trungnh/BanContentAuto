# Evidence: ADR-019 Semantic Footage Gate (proj_f2668146 scene mismatch)

Date: 2026-10-31 · Author: agent · Status: implemented, re-render NOT yet executed

## Checks run (actual results)

| Check | Result |
|---|---|
| Baseline `pytest tests` (before changes) | 250 passed |
| `pytest tests/test_footage_relevance_adr019.py tests/test_sourcing_precision.py` | 29 passed |
| `pytest tests` (after changes) | 268 passed (250 + 18 new) |
| Live judge smoke (9router `ag/gemini-3.8-flash-low`) on SCENE_028 | fail, score 0, "video game footage" ✔ |
| `scripts/audit_scene_relevance.py proj_f2668146 --judge` on the **pre-fix** render | flagged 36/37 → `adr019-audit-before.json` |

## Baseline live-judge calibration (pre-fix render)

- The 6 scenes the user flagged (006, 009, 026, 028, 030, 037) **all scored 0/10**.
- The judge also found subject-absent scenes the user did not list: 003/004 (jackal), 007 (lions), 008 (wildebeest), 013 (zebra/lion), 017/018 (talking head).
- Generic but correct hyena footage scored 3–5. Only 012, 015 and 029 reached 6 or higher.
- Because of this, `semantic_judge_min_score` was changed from 6 to **5**. Scenes below 5 that do show the subject are used as best-effort with `needs_review`.

## Residual risks / not yet verified

- The project has **not been re-rendered**. Whether the new pipeline finds better footage for every scene is unverified.
- The app server (port 8000, PID 15372) still runs the old code and must be restarted.
- The scene-term gate may reject good videos whose titles are sparse. Those scenes fall to best-effort or Tier 4 and are flagged, not silently accepted.
- Vision cost: up to 6 judge calls per scene (≈ up to 220 for 37 scenes).

## Re-render attempt (2026-10-31 12:01–12:03)

- The old render (37 scenes, parts, state.json, final.mp4) was backed up to `cache/backups/_backup_proj_f2668146_20261031_1201/`.
- The app was restarted with the new code on port 8001 and the project started with resume=True.
- Result: **YouTube blocked every request** with "Sign in to confirm you're not a bot" (59 errors, 0 videos downloaded). Every query for SCENE_001 failed.
- Action taken: the run was cancelled and the old render restored. The project is back to `COMPLETE`, 37 scenes, with the previous final.mp4. Nothing was bypassed (no cookies, proxies, or spoofing).
- Status: **re-render is blocked by an external access restriction** (YouTube anti-bot).
