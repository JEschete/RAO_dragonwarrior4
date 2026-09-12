from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


class DashboardBridge:
    def __init__(
        self,
        state_directory: Path | None,
        repository_root: Path | None,
        static_document: dict[str, Any],
        *,
        enabled: bool = True,
        launch: bool = True,
    ) -> None:
        self.enabled = enabled and state_directory is not None and repository_root is not None
        self.launch = launch
        self.repository_root = repository_root
        self.root = state_directory / "dashboard" if self.enabled and state_directory else None
        self.static_path = self.root / "static.json" if self.root else None
        self.live_path = self.root / "live.json" if self.root else None
        self.controls_path = self.root / "controls.json" if self.root else None
        self._last_digest = ""
        self._process: subprocess.Popen[bytes] | None = None
        if self.enabled:
            assert self.root is not None and self.static_path is not None
            self.root.mkdir(parents=True, exist_ok=True)
            self._write_json(self.static_path, static_document)
            controls = self.controls()
            controls.setdefault("workspace", "atlas")
            controls.setdefault("completed_features", [])
            controls["dashboard_open"] = True
            assert self.controls_path is not None
            self._write_json(self.controls_path, controls)

    def controls(self) -> dict[str, Any]:
        if self.controls_path is None:
            return {}
        try:
            value = json.loads(self.controls_path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def publish(self, document: dict[str, Any]) -> bool:
        if not self.enabled or self.live_path is None:
            return False
        encoded = json.dumps(
            document,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        digest = hashlib.sha256(encoded).hexdigest()
        changed = digest != self._last_digest
        if changed:
            self._write_bytes(self.live_path, encoded + b"\n")
            self._last_digest = digest
        self._ensure_process()
        return changed

    def close(self) -> None:
        process = self._process
        self._process = None
        if process is not None and process.poll() is None:
            process.terminate()

    def _ensure_process(self) -> None:
        if not self.launch or not self.enabled or self.root is None:
            return
        if self.controls().get("dashboard_open") is False:
            return
        if self._process is not None and self._process.poll() is None:
            return
        assert self.repository_root is not None
        script = self.repository_root / "dashboard.py"
        if not script.is_file():
            return
        creation_flags = (
            getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        )
        try:
            self._process = subprocess.Popen(
                (sys.executable, str(script), "--state-dir", str(self.root)),
                cwd=self.repository_root,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags,
            )
        except OSError:
            self._process = None

    @staticmethod
    def _write_json(path: Path, value: dict[str, Any]) -> None:
        DashboardBridge._write_bytes(
            path,
            (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
        )

    @staticmethod
    def _write_bytes(path: Path, value: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_bytes(value)
        temporary.replace(path)