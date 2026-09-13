from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


DASHBOARD_MODULE = "retroarch_overlay.presentation.qt.dashboard_main"


class DashboardBridge:
    def __init__(
        self,
        state_directory: Path | None,
        repository_root: Path | None,
        static_document: dict[str, Any],
        *,
        enabled: bool = True,
        launch: bool = True,
        restart_delay_seconds: float = 2.0,
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
        self._last_launch_at: float | None = None
        self._restart_delay_seconds = max(0.0, restart_delay_seconds)
        if self.enabled:
            assert self.root is not None and self.static_path is not None
            self.root.mkdir(parents=True, exist_ok=True)
            self._write_json(self.static_path, static_document)
            controls = self.controls()
            controls.setdefault("workspace", "atlas")
            if controls.get("world_map") not in {"world", "gottside", "underworld"}:
                controls["world_map"] = "world"
            controls.setdefault("completed_features", [])
            controls.setdefault("completed_features_by_playthrough", {})
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

    def activate(self) -> None:
        if not self.enabled or self.controls_path is None:
            return
        controls = self.controls()
        controls["dashboard_open"] = True
        self._write_json(self.controls_path, controls)

    def close(self) -> None:
        process = self._process
        self._process = None
        self._last_launch_at = None
        if process is not None and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                process.kill()
                try:
                    process.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    pass
            except OSError:
                pass

    def _ensure_process(self) -> None:
        if not self.launch or not self.enabled or self.root is None:
            return
        if self.controls().get("dashboard_open") is False:
            return
        if self._process is not None:
            if self._process.poll() is None:
                return
            if (
                self._last_launch_at is not None
                and time.monotonic() - self._last_launch_at
                < self._restart_delay_seconds
            ):
                return
        creation_flags = (
            getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        )
        try:
            self._last_launch_at = time.monotonic()
            self._process = subprocess.Popen(
                (
                    sys.executable,
                    "-m",
                    DASHBOARD_MODULE,
                    "--state-dir",
                    str(self.root),
                ),
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
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=f"{path.name}.",
                suffix=".tmp",
                dir=path.parent,
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                temporary.write(value)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, path)
        except BaseException:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise