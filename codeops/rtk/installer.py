"""
RTK Manager — управление установкой и настройкой RTK.

Обеспечивает:
    - Поиск существующего бинарника RTK
    - Загрузку RTK из GitHub Releases
    - Регистрацию хуков для Claude Code, Cursor, Gemini, Copilot
    - Проверку версии и обновление
    - Инжекцию RTK-инструкций в агентские конфиги
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

RTK_DEFAULT_VERSION = "0.28.2"
RTK_REPO = os.environ.get("RTK_REPO_URL", "https://github.com/rtk-ai/rtk")
RTK_MANAGED_DIR = Path.home() / ".codeops" / "bin"


class RTKManager:
    def __init__(self, binary_path: str | None = None, version: str = RTK_DEFAULT_VERSION):
        self._binary_path = binary_path
        self.version = version
        self._found_path: str | None = None

    @property
    def binary_path(self) -> str | None:
        if self._found_path:
            return self._found_path
        self._found_path = self._resolve()
        return self._found_path

    def is_installed(self) -> bool:
        return self.binary_path is not None

    def ensure_installed(self, auto_install: bool = True) -> str:
        path = self.binary_path
        if path:
            return path
        if auto_install:
            return self.install()
        raise FileNotFoundError(
            "RTK not found. Install with 'codeops rtk install' "
            "or download from https://github.com/rtk-ai/rtk/releases"
        )

    def install(self) -> str:
        path = self._find_system_rtk()
        if path:
            self._found_path = path
            return path

        path = self._download_managed()
        self._found_path = str(path)
        return str(path)

    def register_hooks(self, agent: str = "claude") -> bool:
        rtk = self.ensure_installed()
        try:
            result = subprocess.run(
                [rtk, "init", "--global", f"--{agent}"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def inject_instructions(self, filepath: str | Path) -> bool:
        path = Path(filepath)
        if not path.exists():
            return False

        content = path.read_text()
        if "<!-- headroom:rtk-instructions -->" in content:
            return True

        instructions = self._rtk_instruction_block()
        path.write_text(instructions + "\n\n" + content)
        return True

    def get_stats(self, scope: str = "global") -> dict:
        rtk = self.ensure_installed(auto_install=False)
        try:
            import json
            # Real RTK (>= 0.28) gain command: no --global flag, --format json
            args = [rtk, "gain", "--format", "json"]
            result = subprocess.run(args, capture_output=True, text=True, timeout=30)
            if result.returncode == 0 and result.stdout.strip():
                data = json.loads(result.stdout)
                # Normalize real RTK format → internal format
                summary = data.get("summary", data)
                return {
                    "runs": summary.get("total_commands", 0),
                    "saved_chars": summary.get("total_saved", 0),
                    "raw_chars": summary.get("total_input", 0),
                    "compressed_chars": summary.get("total_output", 0),
                    "compression_ratio": round(summary.get("avg_savings_pct", 0.0), 1),
                    "tokens_saved_estimate": summary.get("total_saved", 0),
                }
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            pass
        except Exception:
            pass
        return {}

    def _resolve(self) -> str | None:
        if self._binary_path:
            expanded = os.path.expanduser(self._binary_path)
            if Path(expanded).exists():
                return expanded

        path = self._find_managed()
        if path:
            return str(path)

        return self._find_system_rtk()

    def _find_system_rtk(self) -> str | None:
        rtk_path = shutil.which("rtk")
        if rtk_path:
            return rtk_path

        managed = self._find_managed()
        if managed:
            return str(managed)
        return None

    def _find_managed(self) -> Path | None:
        candidate = RTK_MANAGED_DIR / "rtk"
        if candidate.exists():
            return candidate
        return None

    def _download_managed(self) -> Path:
        import platform
        import tempfile
        import urllib.request

        system = platform.system().lower()
        machine = platform.machine().lower()

        target_map = {
            ("linux", "x86_64"): "x86_64-unknown-linux-gnu",
            ("linux", "aarch64"): "aarch64-unknown-linux-gnu",
            ("darwin", "x86_64"): "x86_64-apple-darwin",
            ("darwin", "arm64"): "aarch64-apple-darwin",
        }

        target = target_map.get((system, machine))
        if target is None:
            raise RuntimeError(f"Unsupported platform: {system}/{machine}")

        ext = ".tar.gz"
        archive_name = f"rtk-{target}{ext}"
        url = f"{RTK_REPO}/releases/download/v{self.version}/{archive_name}"

        RTK_MANAGED_DIR.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / archive_name
            urllib.request.urlretrieve(url, archive_path)

            import tarfile
            with tarfile.open(archive_path, "r:gz") as tf:
                tf.extractall(tmp)

            binary = Path(tmp) / "rtk"
            dest = RTK_MANAGED_DIR / "rtk"
            shutil.copy2(binary, dest)
            dest.chmod(0o755)

        return dest

    @staticmethod
    def _rtk_instruction_block() -> str:
        return """<!-- headroom:rtk-instructions -->
# RTK (Rust Token Killer) - Token-Optimized Commands

When running shell commands, **always prefix with `rtk`**. This reduces context
usage by 60-90% with zero behavior change.

## Key Commands
```bash
rtk git status          rtk git diff            rtk git log
rtk ls <path>           rtk read <file>         rtk grep <pattern>
rtk find <pattern>      rtk diff <file>
rtk pytest tests/       rtk cargo test          rtk test <cmd>
rtk tsc                 rtk lint                rtk cargo build
rtk gh pr view <n>      rtk gh run list         rtk gh issue list
rtk docker ps           rtk kubectl get         rtk docker logs <c>
rtk pip list            rtk pnpm install        rtk npm run <script>
```

## Rules
- In command chains, prefix each segment: `rtk git add . && rtk git commit -m "msg"`
- For debugging, use raw command without rtk prefix
- `rtk proxy <cmd>` runs command without filtering but tracks usage
<!-- /headroom:rtk-instructions -->
"""
