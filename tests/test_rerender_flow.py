"""
Unit test for rerender workflow: state reset, background dispatch, and API response.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from autovideo.api.app import create_app
from autovideo.coordinator import MasterPipelineCoordinator, PipelineStage, ProjectState
from autovideo.core.config import AppConfig
from autovideo.scene_editor import SceneEditor


def test_rerender_flow_resets_state_and_enqueues(tmp_path):
    config = AppConfig.from_base_dir(tmp_path)
    coord = MasterPipelineCoordinator(config=config)
    p = coord.get_or_create_project(
        topic="Test Rerender",
        project_id="proj_test_rerender"
    )
    p.screenplay = {"title": "Test Rerender", "chapters": []}
    p.stage = PipelineStage.COMPLETE
    p.progress = 100.0
    p.final_video_path = str(tmp_path / "final.mp4")
    (tmp_path / "final.mp4").write_bytes(b"dummy")

    app = create_app(config=config, coordinator=coord)
    client = TestClient(app)

    with patch.object(coord, "enqueue_project") as mock_enqueue:
        mock_enqueue.return_value = {"status": "started", "project_id": "proj_test_rerender"}
        res = client.post("/api/projects/proj_test_rerender/rerender")
        assert res.status_code == 200
        data = res.json()
        assert "backup_dir" in data

        # Check that state was reset to B2_SOURCING_TTS
        assert p.stage == PipelineStage.B2_SOURCING_TTS
        assert p.progress == 25.0
        assert p.final_video_path is None
        mock_enqueue.assert_called_once_with(project_id="proj_test_rerender", resume=True)
