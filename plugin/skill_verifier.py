"""Verify process-type plugin skills are registered and discoverable."""

from __future__ import annotations
from pathlib import Path
import os
import yaml


def verify_process_type_skills(process_type: str) -> tuple[list[str], list[str], list[str]]:
    """Return (found, missing, errors) for a process_type's declared skills.

    Reads ``provides_skills`` from ``plugin.yaml`` of the plugin registered
    for *process_type*, then verifies each skill's SKILL.md exists at the
    resolved path under ``$HERMES_HOME/plugins/<name>/plugin/skills/``.
    """
    hermes_home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
    plugins_dir = hermes_home / "plugins"

    found: list[str] = []
    missing: list[str] = []
    errors: list[str] = []

    # Find plugin with matching process_type hook
    plugin_name = None
    plugin_skills: list[str] = []
    for child in sorted(plugins_dir.iterdir()):
        manifest = child / "plugin.yaml"
        if not manifest.is_file():
            continue
        try:
            data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
        except Exception:
            continue
        hooks = data.get("provides_hooks", [])
        for hook in hooks:
            if hook == f"process_type:{process_type}":
                plugin_name = child.name
                plugin_skills = data.get("provides_skills", [])
                break
        if plugin_name:
            break

    if not plugin_name:
        errors.append(f"No plugin found for process_type: {process_type}")
        return found, missing, errors

    skills_dir = plugins_dir / plugin_name / "plugin" / "skills"
    for skill in plugin_skills:
        skill_md = skills_dir / skill / "SKILL.md"
        if skill_md.is_file():
            found.append(skill)
        else:
            missing.append(skill)

    return found, missing, errors
