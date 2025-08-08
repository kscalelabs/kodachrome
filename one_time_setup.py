#!/usr/bin/env python3
"""One-time setup script for this template.

Reads values from `one_time_setup_config.yaml` and updates files accordingly.
Safe to run once on a fresh clone of this template. Make sure your working tree is clean.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    import yaml  # type: ignore
except Exception as exc:  # pragma: no cover
    print("ERROR: This script requires PyYAML. Install with: pip install pyyaml", file=sys.stderr)
    raise


REPO_ROOT = Path(__file__).resolve().parent


@dataclass
class SetupConfig:
    distribution_name: str
    import_name: str
    description: str
    url: str
    author: str
    author_email: Optional[str]
    python_min_version: str
    version: str
    default_branch: str
    year: str

    @staticmethod
    def from_yaml(path: Path) -> "SetupConfig":
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

        def require(key: str) -> str:
            val = data.get(key)
            if not val or not isinstance(val, (str, int)):
                raise ValueError(f"Missing or invalid '{key}' in {path}")
            return str(val)

        return SetupConfig(
            distribution_name=require("distribution_name"),
            import_name=require("import_name"),
            description=require("description"),
            url=require("url"),
            author=require("author"),
            author_email=str(data.get("author_email") or "" ) or None,
            python_min_version=require("python_min_version"),
            version=require("version"),
            default_branch=require("default_branch"),
            year=require("year"),
        )


def assert_valid_import_name(name: str) -> None:
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", name):
        raise ValueError(f"Invalid Python import name: {name}")


def pyproject_target_version(python_min_version: str) -> str:
    m = re.match(r"^(\d+)\.(\d+)$", python_min_version.strip())
    if not m:
        raise ValueError("python_min_version must be like '3.11'")
    return f"py{m.group(1)}{m.group(2)}"


def rename_package_dir(current: str, new: str) -> None:
    if current == new:
        return
    src = REPO_ROOT / current
    dst = REPO_ROOT / new
    if not src.exists():
        # Already renamed or template changed; nothing to do
        return
    if dst.exists():
        raise FileExistsError(f"Target package directory already exists: {dst}")
    src.rename(dst)


def rewrite_file(path: Path, transform: callable[[str], str]) -> None:
    text = path.read_text(encoding="utf-8")
    new_text = transform(text)
    if text != new_text:
        path.write_text(new_text, encoding="utf-8")


def update_setup_py(cfg: SetupConfig) -> None:
    path = REPO_ROOT / "setup.py"
    if not path.exists():
        return

    def _x(s: str) -> str:
        s = re.sub(r'name\s*=\s*"[^"]*"', f'name="{cfg.distribution_name}"', s)
        s = re.sub(r'description\s*=\s*"[^"]*"', f'description="{cfg.description}"', s)
        s = re.sub(r'author\s*=\s*"[^"]*"', f'author="{cfg.author}"', s)
        if cfg.author_email:
            if "author_email" in s:
                s = re.sub(r'author_email\s*=\s*"[^"]*"', f'author_email="{cfg.author_email}"', s)
            else:
                # Insert author_email after author
                s = re.sub(
                    r'(author\s*=\s*"[^"]*",\n)',
                    r"\1    author_email=\"" + re.escape(cfg.author_email) + r"\",\n",
                    s,
                )
        s = re.sub(r'url\s*=\s*"[^"]*"', f'url="{cfg.url}"', s)
        s = re.sub(r'python_requires\s*=\s*"[^"]*"', f'python_requires=">={cfg.python_min_version}"', s)
        # Update template_package path references to new import_name
        s = s.replace('"template_package/requirements.txt"', f'"{cfg.import_name}/requirements.txt"')
        s = s.replace('"template_package/__init__.py"', f'"{cfg.import_name}/__init__.py"')
        return s

    rewrite_file(path, _x)


def update_pyproject_toml(cfg: SetupConfig) -> None:
    path = REPO_ROOT / "pyproject.toml"
    if not path.exists():
        return

    tgt = pyproject_target_version(cfg.python_min_version)

    def _x(s: str) -> str:
        s = re.sub(r'target-version\s*=\s*"[^"]*"', f'target-version = "{tgt}"', s)
        s = re.sub(
            r'known-first-party\s*=\s*\[[^\]]*\]',
            f'known-first-party = ["{cfg.import_name}", "tests"]',
            s,
        )
        return s

    rewrite_file(path, _x)


def update_manifest_in(cfg: SetupConfig) -> None:
    path = REPO_ROOT / "MANIFEST.in"
    if not path.exists():
        return

    def _x(s: str) -> str:
        s = s.replace("recursive-include template_package/", f"recursive-include {cfg.import_name}/")
        return s

    rewrite_file(path, _x)


def update_makefile(cfg: SetupConfig) -> None:
    path = REPO_ROOT / "Makefile"
    if not path.exists():
        return

    def _x(s: str) -> str:
        # Update displayed project name and Python version in help text
        s = s.replace("template_package", cfg.distribution_name)
        s = re.sub(r"python=\d+\.\d+", f"python={cfg.python_min_version}", s)
        return s

    rewrite_file(path, _x)


def update_license(cfg: SetupConfig) -> None:
    path = REPO_ROOT / "LICENSE"
    if not path.exists():
        return

    def _x(s: str) -> str:
        s = re.sub(r"Copyright \(c\) \d+ .*", f"Copyright (c) {cfg.year} {cfg.author}", s)
        return s

    rewrite_file(path, _x)


def update_workflows(cfg: SetupConfig) -> None:
    workflows_dir = REPO_ROOT / ".github" / "workflows"
    if not workflows_dir.exists():
        return

    def fix_python_version(s: str) -> str:
        return re.sub(r'python-version:\s*"[^"]*"', f'python-version: "{cfg.python_min_version}"', s)

    def fix_default_branch(s: str) -> str:
        # Update branch triggers in test workflow (push/pull_request)
        s = re.sub(r"branches:\n\s*-\s*\w+", f"branches:\n      - {cfg.default_branch}", s)
        return s

    for name in ("test.yml", "publish.yml"):
        path = workflows_dir / name
        if not path.exists():
            continue
        def _x(s: str) -> str:
            s = fix_python_version(s)
            if name == "test.yml":
                s = fix_default_branch(s)
            return s
        rewrite_file(path, _x)


def update_init_version(cfg: SetupConfig) -> None:
    pkg_dir = REPO_ROOT / cfg.import_name
    init_py = pkg_dir / "__init__.py"
    if not init_py.exists():
        return

    def _x(s: str) -> str:
        s = re.sub(r'__version__\s*=\s*"[^"]*"', f'__version__ = "{cfg.version}"', s)
        return s

    rewrite_file(init_py, _x)


def main() -> None:
    config_path = REPO_ROOT / "one_time_setup_config.yaml"
    cfg = SetupConfig.from_yaml(config_path)
    assert_valid_import_name(cfg.import_name)

    # 1) Rename package dir before editing file paths
    rename_package_dir("template_package", cfg.import_name)

    # 2) Update files
    update_setup_py(cfg)
    update_pyproject_toml(cfg)
    update_manifest_in(cfg)
    update_makefile(cfg)
    update_license(cfg)
    update_workflows(cfg)
    update_init_version(cfg)

    print("One-time setup complete. Review changes and commit them.")


if __name__ == "__main__":  # pragma: no cover
    main() 