"""
Pipeline state — checkpoint every agent output to disk.

Creates a session directory per run so the harness can resume from any
completed step after a crash, rather than re-running all upstream agents.

Session dir: {output_dir}/{safe_name}_session/
Each step saves its output as {step}.json (dicts) or {step}.md (strings).
"""

import json
from pathlib import Path
from typing import Any, Optional


class PipelineState:
    """Saves and loads per-agent checkpoints for crash recovery."""

    def __init__(self, session_dir: str | Path):
        self._dir = Path(session_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    @property
    def session_dir(self) -> Path:
        return self._dir

    def completed(self, step: str) -> bool:
        return (self._dir / f"{step}.json").exists() or \
               (self._dir / f"{step}.md").exists()

    def save(self, step: str, data: Any) -> None:
        if isinstance(data, str):
            (self._dir / f"{step}.md").write_text(data, encoding="utf-8")
        else:
            (self._dir / f"{step}.json").write_text(
                json.dumps(data, indent=2, default=str), encoding="utf-8"
            )

    def load(self, step: str) -> Optional[Any]:
        json_path = self._dir / f"{step}.json"
        md_path = self._dir / f"{step}.md"
        if json_path.exists():
            return json.loads(json_path.read_text(encoding="utf-8"))
        if md_path.exists():
            return md_path.read_text(encoding="utf-8")
        return None

    def completed_steps(self) -> list[str]:
        steps = []
        for f in sorted(self._dir.iterdir()):
            if f.suffix in (".json", ".md"):
                steps.append(f.stem)
        return steps
