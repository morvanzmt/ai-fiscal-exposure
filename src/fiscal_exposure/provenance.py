"""Provenance.

Each pipeline step records the files it read, the files it wrote, their SHA-256
digests, and the parameters in force, appending to a JSON manifest. Any figure in
``output/`` can therefore be tied back to the exact inputs that produced it.
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CHUNK = 1 << 20


def file_digest(path: str | Path, algorithm: str = "sha256") -> str:
    """SHA-256 of a file, streamed so large microdata files do not blow memory."""
    h = hashlib.new(algorithm)
    with Path(path).open("rb") as fh:
        while chunk := fh.read(CHUNK):
            h.update(chunk)
    return f"{algorithm}:{h.hexdigest()}"


def _git_revision() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


@dataclass
class StepRecord:
    step: str
    started_at: str
    finished_at: str | None = None
    inputs: dict[str, str] = field(default_factory=dict)
    outputs: dict[str, str] = field(default_factory=dict)
    params: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    git_revision: str | None = None
    python: str = field(default_factory=platform.python_version)


class Manifest:
    """Append-only record of pipeline steps.

    Usage::

        with Manifest(cfg.paths.manifest).step("03_merge", params=...) as rec:
            rec.add_input(exposure_path)
            ...
            rec.add_output(out_path)
            rec.metric("crosswalk_coverage", 0.97)
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8") as fh:
            try:
                return json.load(fh)
            except json.JSONDecodeError:
                return []

    def _write(self, records: list[dict[str, Any]]) -> None:
        with self.path.open("w", encoding="utf-8") as fh:
            json.dump(records, fh, indent=2, sort_keys=False)
            fh.write("\n")

    def step(self, name: str, params: dict[str, Any] | None = None) -> _StepCtx:
        return _StepCtx(self, name, params or {})

    def append(self, record: StepRecord) -> None:
        records = self._load()
        records.append(asdict(record))
        self._write(records)

    def records(self) -> list[dict[str, Any]]:
        return self._load()


class _StepCtx:
    def __init__(self, manifest: Manifest, name: str, params: dict[str, Any]) -> None:
        self._manifest = manifest
        self.record = StepRecord(
            step=name,
            started_at=datetime.now(UTC).isoformat(timespec="seconds"),
            params=params,
            git_revision=_git_revision(),
        )

    def __enter__(self) -> _StepCtx:
        return self

    def add_input(self, path: str | Path) -> None:
        p = Path(path)
        self.record.inputs[str(p)] = file_digest(p) if p.exists() else "MISSING"

    def add_output(self, path: str | Path) -> None:
        p = Path(path)
        self.record.outputs[str(p)] = file_digest(p) if p.exists() else "MISSING"

    def metric(self, key: str, value: Any) -> None:
        self.record.metrics[key] = value

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.record.finished_at = datetime.now(UTC).isoformat(timespec="seconds")
        if exc_type is not None:
            self.record.metrics["error"] = f"{exc_type.__name__}: {exc}"
        self._manifest.append(self.record)
        return False
