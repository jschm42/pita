"""Unit tests for the project manager service."""

import pytest

from src.core import project_manager
from src.core.models import ProjectConfig, TestCase


def test_project_manager_lifecycle(
    tmp_path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies list, save, load, and delete lifecycle of project configs."""
    # Point the projects directory to a temporary path
    monkeypatch.setattr(project_manager, "get_projects_dir", lambda: str(tmp_path))

    # 1. Initially projects list should be empty
    assert project_manager.list_projects() == []

    # 2. Create and save a new project config
    test_case = TestCase(name="Login Test", description="Try to log in")
    config = ProjectConfig(
        name="Test Project One",
        target_url="https://example.com",
        model="openai/gpt-4",
        api_base="http://localhost:8080",
        max_steps=10,
        credentials={"username": "user", "password": "pass"},
        tests=[test_case],
    )

    project_manager.save_project(config)

    # 3. List projects should now return our project (with space in name)
    assert project_manager.list_projects() == ["Test Project One"]

    # 4. Load the project and verify contents
    loaded = project_manager.load_project("Test Project One")
    assert loaded.name == "Test Project One"
    assert loaded.target_url == "https://example.com"
    assert loaded.model == "openai/gpt-4"
    assert loaded.api_base == "http://localhost:8080"
    assert loaded.max_steps == 10
    assert loaded.credentials == {"username": "user", "password": "pass"}
    assert len(loaded.tests) == 1
    assert loaded.tests[0].name == "Login Test"
    assert loaded.tests[0].description == "Try to log in"

    # 5. Delete project
    project_manager.delete_project("Test Project One")
    assert project_manager.list_projects() == []

    with pytest.raises(FileNotFoundError):
        project_manager.load_project("Test Project One")
