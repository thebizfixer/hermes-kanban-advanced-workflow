#!/usr/bin/env python3
"""Validate .hermes/kanban-overrides/kanban-config.yaml against schema/kanban-config.schema.json."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SUPPORTED_SCHEMA_VERSIONS = frozenset({"1.0.0"})


def _load_yaml_simple(path: Path) -> dict[str, str]:
    """Minimal YAML loader for flat key: value overlay files (no nested structures)."""
    data: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("# yaml-language-server"):
            continue
        if line[:1].isspace():
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if "#" in value:
            value = value.split("#", 1)[0].strip()
        value = value.strip("\"'")
        if key and value:
            data[key] = value
    return data


def _validate(data: dict[str, str], schema: dict) -> list[str]:
    errors: list[str] = []
    required = schema.get("required", [])
    props = schema.get("properties", {})
    additional = schema.get("additionalProperties", True)

    for req in required:
        if req not in data:
            errors.append(f"missing required key: {req}")

    for key in data:
        if key not in props:
            if additional is False:
                errors.append(f"unknown key: {key}")
            continue
        spec = props[key]
        val = data[key]
        if spec.get("type") == "integer":
            try:
                int(val)
            except ValueError:
                errors.append(f"{key}: expected integer, got {val!r}")
        if "pattern" in spec and not re.fullmatch(spec["pattern"], val):
            errors.append(f"{key}: does not match pattern {spec['pattern']}")

    sv = data.get("schema_version")
    if sv and sv not in SUPPORTED_SCHEMA_VERSIONS:
        errors.append(
            f"schema_version {sv!r} not supported (supported: {', '.join(sorted(SUPPORTED_SCHEMA_VERSIONS))})"
        )
    return errors


def main() -> int:
    script_dir = Path(__file__).resolve().parent
    bundle_dir = script_dir.parent
    schema_path = bundle_dir / "schema" / "kanban-config.schema.json"

    if len(sys.argv) < 2:
        print("Usage: validate_config.py <path-to-kanban-config.yaml>", file=sys.stderr)
        return 2

    config_path = Path(sys.argv[1]).resolve()
    if not config_path.is_file():
        print(f"ERROR: config not found: {config_path}", file=sys.stderr)
        return 1

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    data = _load_yaml_simple(config_path)
    errors = _validate(data, schema)

    if errors:
        print(f"FAIL: {config_path}", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print(f"OK: {config_path} (schema_version={data.get('schema_version', '?')})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
