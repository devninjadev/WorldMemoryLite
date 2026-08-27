"""Build a deterministic, installable World Memory skill archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Iterable
import zipfile


VERSION = "0.14.5"
PACKAGE_NAME = "world-memory-autopilot"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PACKAGE = PROJECT_ROOT / PACKAGE_NAME
DEFAULT_OUTPUT = PROJECT_ROOT / f"{PACKAGE_NAME}-v{VERSION}.zip"
_REQUIRED_RELATIVE_FILES = frozenset(
    {
        "SKILL.md",
        "requirements.txt",
        "agents/openai.yaml",
        "assets/icon.svg",
        "references/collection-and-analysis.md",
        "references/deployment.md",
        "references/market-data.md",
        "references/notion-layout.md",
        "scripts/world_memory/__init__.py",
        "scripts/world_memory/__main__.py",
        "scripts/world_memory/bootstrap.py",
        "scripts/world_memory/cli.py",
        "scripts/world_memory/discovery.py",
        "scripts/world_memory/feed.py",
        "scripts/world_memory/feed_pages.py",
        "scripts/world_memory/llm_plan.py",
        "scripts/world_memory/market.py",
        "scripts/world_memory/notion_layout.py",
        "scripts/world_memory/notion_payloads.py",
        "scripts/world_memory/plugin_market.py",
        "scripts/world_memory/registry.py",
        "scripts/world_memory/windows.py",
        "scripts/world_memory/views.py",
        "scripts/world_memory/workflow.py",
    }
)
_ALLOWED_ROOTS = frozenset({"SKILL.md", "requirements.txt", "agents", "assets", "references", "scripts"})
_LEGACY_MARKERS = (
    "targeted-v1",
    "wmc1",
    "Cache Reconciled",
    "Payload Digest",
    "Run Key",
    "Slot Key",
    "precommit",
    "postcommit",
    "0.10.x",
)
_UUID = re.compile(
    r"(?i)(?<![0-9a-f])[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}(?![0-9a-f])"
)
_SECRETS = (
    re.compile(r"(?i)Bearer\s+[A-Za-z0-9._-]{16,}"),
    re.compile(r"(?i)sk-[A-Za-z0-9_-]{16,}"),
)
_VERSIONED_ARCHIVE_NAME = re.compile(
    rf"^{re.escape(PACKAGE_NAME)}-v[0-9]+(?:\.[0-9]+){{2}}\.zip$"
)


def _safe_error(category: str) -> ValueError:
    return ValueError(category)


def _relative_files(package_dir: Path) -> list[Path]:
    if not package_dir.is_dir() or package_dir.is_symlink():
        raise _safe_error("invalid-package")
    discovered: list[Path] = []
    for path in package_dir.rglob("*"):
        relative = path.relative_to(package_dir)
        if path.is_symlink():
            raise _safe_error("symlink-not-allowed")
        if any(part.startswith(".") for part in relative.parts):
            raise _safe_error("hidden-file-not-allowed")
        if relative.parts[0] in _ALLOWED_ROOTS and path.is_dir() and path.name == "__pycache__":
            continue
        if relative.parts[0] in _ALLOWED_ROOTS and path.is_file() and path.suffix == ".pyc":
            continue
        if not path.is_file():
            if not path.is_dir():
                raise _safe_error("unsupported-file-type")
            continue
        if relative.parts[0] not in _ALLOWED_ROOTS:
            continue
        relative_text = relative.as_posix()
        if relative_text not in _REQUIRED_RELATIVE_FILES:
            raise _safe_error("unexpected-installable-file")
        discovered.append(relative)
    discovered_set = frozenset(path.as_posix() for path in discovered)
    if discovered_set != _REQUIRED_RELATIVE_FILES:
        raise _safe_error("missing-required-file")
    return sorted(discovered)


def _validate_content(package_dir: Path, relative_files: Iterable[Path]) -> None:
    skill = (package_dir / "SKILL.md").read_text(encoding="utf-8")
    if f"Version: `{VERSION}`" not in skill or "notion-native-v2" not in skill:
        raise _safe_error("version-drift")
    for relative in relative_files:
        text = (package_dir / relative).read_text(encoding="utf-8")
        if any(marker in text for marker in _LEGACY_MARKERS):
            raise _safe_error("legacy-runtime-marker")
        if _UUID.search(text) or any(pattern.search(text) for pattern in _SECRETS):
            raise _safe_error("sensitive-content")


def _validate_output(package_dir: Path, output: Path) -> None:
    if not output.parent.is_dir():
        raise _safe_error("output-parent-missing")
    if output.exists() and output.is_dir():
        raise _safe_error("invalid-output")
    try:
        resolved_output = output.resolve(strict=False)
        resolved_package = package_dir.resolve(strict=True)
    except OSError as exc:
        raise _safe_error("invalid-output") from exc
    if resolved_output == resolved_package or resolved_package in resolved_output.parents:
        raise _safe_error("output-aliases-source")
    if output.exists() and output.is_symlink():
        raise _safe_error("invalid-output")


def _verify_archive(archive_path: Path, package_dir: Path, relative_files: Iterable[Path]) -> None:
    expected = [f"{PACKAGE_NAME}/{relative.as_posix()}" for relative in relative_files]
    with zipfile.ZipFile(archive_path) as archive:
        if archive.testzip() is not None or archive.namelist() != expected:
            raise _safe_error("archive-verification-failed")
        for relative in relative_files:
            if archive.read(f"{PACKAGE_NAME}/{relative.as_posix()}") != (package_dir / relative).read_bytes():
                raise _safe_error("archive-verification-failed")


def _write_archive(package_dir: Path, output: Path, relative_files: Iterable[Path]) -> bytes:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(
            temporary,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
            strict_timestamps=True,
        ) as archive:
            for relative in relative_files:
                info = zipfile.ZipInfo(f"{PACKAGE_NAME}/{relative.as_posix()}", date_time=(1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, (package_dir / relative).read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        _verify_archive(temporary, package_dir, relative_files)
        payload = temporary.read_bytes()
        os.replace(temporary, output)
        return payload
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def build_release(package_dir: Path, output: Path) -> dict[str, object]:
    """Validate ``package_dir`` and atomically create a deterministic ZIP."""

    package = Path(package_dir)
    destination = Path(output)
    _validate_output(package, destination)
    relative_files = _relative_files(package)
    _validate_content(package, relative_files)
    payload = _write_archive(package, destination, relative_files)
    pruned_archives = _prune_legacy_sibling_archives(destination)
    entries = [f"{PACKAGE_NAME}/{relative.as_posix()}" for relative in relative_files]
    return {
        "version": VERSION,
        "topLevel": [PACKAGE_NAME],
        "entries": entries,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "size": len(payload),
        "prunedArchives": pruned_archives,
    }


def _prune_legacy_sibling_archives(output: Path) -> list[str]:
    target_name = f"{PACKAGE_NAME}-v{VERSION}.zip"
    if output.name != target_name:
        return []
    removed: list[str] = []
    for sibling in sorted(output.parent.iterdir(), key=lambda path: path.name):
        if (
            sibling == output
            or sibling.is_symlink()
            or not sibling.is_file()
            or _VERSIONED_ARCHIVE_NAME.fullmatch(sibling.name) is None
        ):
            continue
        sibling.unlink()
        removed.append(sibling.name)
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the World Memory skill release ZIP.")
    parser.add_argument("--package", default=str(DEFAULT_PACKAGE))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    arguments = parser.parse_args()
    try:
        receipt = build_release(Path(arguments.package), Path(arguments.output))
    except (OSError, ValueError):
        print("release-build-error", file=os.sys.stderr)
        return 2
    print(json.dumps(receipt, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
