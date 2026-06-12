"""Project manager service for loading, saving, and listing configurations.

This module encapsulates all file system interactions for project configurations.
"""

import os

from src.core.models import ProjectConfig


def get_projects_dir() -> str:
    """Resolves and ensures the projects directory exists in the workspace root."""
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    projects_dir = os.path.join(root_dir, "projects")
    os.makedirs(projects_dir, exist_ok=True)
    return projects_dir


def get_project_file_path(project_name: str) -> str:
    """Returns the absolute file path for a project configuration file."""
    # Convert name to a safe filename (remove trailing spaces, check extensions)
    safe_name = "".join(
        c for c in project_name if c.isalnum() or c in (" ", "_", "-")
    ).strip()
    safe_name = safe_name.replace(" ", "_")
    return os.path.join(get_projects_dir(), f"{safe_name}.json")


def list_projects() -> list[str]:
    """Lists the names of all saved projects in the projects folder."""
    projects_dir = get_projects_dir()
    project_files = [
        f
        for f in os.listdir(projects_dir)
        if f.endswith(".json") and os.path.isfile(os.path.join(projects_dir, f))
    ]
    # Extract names by stripping .json suffix and converting underscores back to spaces for presentation
    names = []
    for f in project_files:
        base_name = os.path.splitext(f)[0]
        display_name = base_name.replace("_", " ")
        names.append(display_name)
    return sorted(names)


def load_project(project_name: str) -> ProjectConfig:
    """Loads a project configuration from disk by name.

    Args:
        project_name: The display or file name of the project.

    Returns:
        The validated ProjectConfig object.

    Raises:
        FileNotFoundError: If the project JSON does not exist.
    """
    path = get_project_file_path(project_name)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Project config file not found at {path}")

    with open(path, encoding="utf-8") as f:
        raw_json = f.read()
    return ProjectConfig.model_validate_json(raw_json)


def save_project(config: ProjectConfig) -> None:
    """Saves a project configuration to disk as JSON.

    Args:
        config: The ProjectConfig instance to write.
    """
    path = get_project_file_path(config.name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(config.model_dump_json(indent=2))


def delete_project(project_name: str) -> None:
    """Deletes a project configuration file from disk.

    Args:
        project_name: Name of the project to delete.
    """
    path = get_project_file_path(project_name)
    if os.path.exists(path):
        os.remove(path)
