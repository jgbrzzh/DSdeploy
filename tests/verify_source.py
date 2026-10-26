"""Source-level integration: upstream config, password hashing and actual ORM.

Run after cloning upstream into .research and installing sqlmodel, aiosqlite,
deprecated and pyyaml in an isolated verification environment.
Does not start containers or claim QQ runtime acceptance.
"""
import asyncio
import importlib.util
import json
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / ".research/AstrBot/astrbot"
sys.path.insert(0, str(SOURCE.parent))
# Bypass only application package startup; imported submodules and ORM below
# are the actual upstream files. This is not a full application startup test.
for name, directory in [("astrbot.core", SOURCE / "core"),
                        ("astrbot.core.config", SOURCE / "core/config")]:
    module = types.ModuleType(name)
    module.__path__ = [str(directory)]
    sys.modules[name] = module
spec = importlib.util.spec_from_file_location("bootstrap_under_test", ROOT / "bootstrap/bootstrap.py")
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)

from astrbot.core.config.default import DEFAULT_CONFIG
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.utils.auth_password import (
    hash_dashboard_password, hash_md5_dashboard_password, verify_dashboard_password,
)
import yaml


async def main():
    settings = dict(owner_qq="12345678", bot_qq="87654321", model="deepseek-flash",
                    api_base="https://api.deepseek.com/v1", api_key="test-not-a-real-key",
                    onebot_token="test-token", dashboard_password="Whale!0123456789abcdef", jwt_secret="test-jwt")
    before = json.dumps(DEFAULT_CONFIG, sort_keys=True)
    with tempfile.TemporaryDirectory(dir=ROOT / '.research') as folder:
        data = Path(folder)
        bootstrap.install_plugins(data, settings, ROOT / ".research/extracted-plugins")
        memory_file = data / "config/astrbot_plugin_livingmemory_config.json"
        proactive_file = data / "config/astrbot_plugin_proactive_chat_config.json"
        memory = json.loads(memory_file.read_text(encoding="utf-8"))
        proactive = json.loads(proactive_file.read_text(encoding="utf-8"))
        assert memory["provider_settings"]["embedding_provider_id"] == "bge_m3_local"
        assert memory["access_control"]["allowed_ids"] == "qq:FriendMessage:12345678"
        assert memory["filtering_settings"]["memory_scope_mode"] == "session"
        assert memory["agent_tools"]["enable_memorize_tool"]
        assert proactive["friend_settings"]["session_list"] == ["qq:FriendMessage:12345678"]
        assert proactive["friend_settings"]["schedule_settings"]["quiet_hours"] == "23-8"
        assert not proactive["group_settings"]["enable"]
        assert not proactive["web_admin"]["enabled"]
        saved_plugin_config = proactive_file.read_bytes()
        bootstrap.install_plugins(data, {**settings, "owner_qq": "99999999"}, ROOT / ".research/extracted-plugins")
        assert proactive_file.read_bytes() == saved_plugin_config
        await bootstrap.initialize(data, settings, "测试大肥鱼人格")
        config = json.loads((data / "cmd_config.json").read_text(encoding="utf-8"))
        assert config["agent_runner"]["config"]["model"]["provider_id"] == "deepseek/deepseek-flash"
        assert config["platform_settings"]["id_whitelist"] == ["qq:FriendMessage:12345678"]
        assert verify_dashboard_password(config["dashboard"]["pbkdf2_password"], settings["dashboard_password"])
        db = SQLiteDatabase(str(data / "data_v4.db"))
        await db.initialize()
        persona = await db.get_persona_by_id("dafeiyu")
        assert persona.system_prompt == "测试大肥鱼人格"
        assert persona.tools == ["recall_long_term_memory", "memorize_long_term_memory"] and persona.skills == []
        await db.engine.dispose()
        content = (data / "cmd_config.json").read_bytes()
        await bootstrap.initialize(data, {**settings, "api_key": "changed"}, "changed")
        assert (data / "cmd_config.json").read_bytes() == content
    assert json.dumps(DEFAULT_CONFIG, sort_keys=True) == before
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    assert compose["services"]["astrbot"]["ports"] == ["127.0.0.1:6185:6185"]
    assert compose["services"]["napcat"]["ports"] == ["127.0.0.1:6099:6099"]
    assert not compose["services"]["ollama"].get("ports")
    print("PASS: upstream defaults + password hashes + SQLite persona + bundled plugin configs + restart preservation + YAML")


asyncio.run(main())
