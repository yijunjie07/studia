"""User-local settings. Credentials never belong in the source checkout."""
import json
import os
import tempfile
from pathlib import Path

from ai.client import AIConfig


class SettingsError(RuntimeError):
    pass


def config_directory():
    override = os.environ.get("ICVE_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "icve-ai-assistant"
    return Path.home() / ".config" / "icve-ai-assistant"


class SettingsStore:
    def __init__(self, directory=None):
        self.directory = Path(directory) if directory is not None else config_directory()
        self.path = self.directory / "settings.json"

    def _read(self):
        try:
            if not self.path.exists():
                return {}
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("version", 1) != 1:
                raise ValueError()
            return data
        except (OSError, ValueError):
            raise SettingsError(f"无法读取本机配置，请检查 {self.path}（原文件未覆盖）") from None

    def get(self, key, default=None):
        return self._read().get(key, default)

    def set(self, key, value):
        data = self._read()
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
        data["version"] = 1
        temporary = None
        try:
            self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(prefix=".settings-", dir=self.directory)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                os.chmod(temporary, 0o600)
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        except OSError:
            raise SettingsError("无法保存本机配置，请检查配置目录权限；旧配置未被覆盖") from None
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)

    def ai_config(self):
        data = self.get("ai")
        if data is None:
            return None
        try:
            if not isinstance(data, dict):
                raise ValueError()
            return AIConfig(data["base_url"], data["model"], data["api_key"])
        except (KeyError, TypeError, ValueError, AttributeError):
            raise SettingsError("保存的 AI 配置无效，请在本机设置中重新配置或清除") from None

    def save_ai(self, config):
        self.set("ai", {"base_url": config.base_url, "model": config.model, "api_key": config.api_key})

    def session(self, platform):
        data = self.get("session_" + platform)
        if isinstance(data, dict) and isinstance(data.get("access_token"), str) and data["access_token"]:
            return data
        return None

    def save_session(self, platform, client):
        self.set("session_" + platform, {"access_token": client.access_token})

    def clear_session(self, platform):
        self.set("session_" + platform, None)
