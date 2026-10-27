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
import zipfile
import io
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
        assert proactive['friend_settings']['context_settings']['source_mode'] == 'hybrid'
        assert proactive['friend_settings']['segmented_reply_settings']['enable']
        assert proactive['friend_settings']['schedule_settings']['max_unanswered_times'] == 3
        meme = json.loads((data / 'config/meme_manager_config.json').read_text(encoding='utf-8'))
        assert meme['generation']['trigger']['scope'] == 'chat_and_plugin_llm'
        assert meme['generation']['emotion']['llm']['provider_id'] == 'deepseek/deepseek-flash'
        assert not meme['auto_collect']['enabled']
        signin = json.loads((data / 'config/astrbot_plugin_signin_config.json').read_text(encoding='utf-8'))
        assert signin['admin_umo_list'] == settings['owner_qq']
        saved_plugin_config = proactive_file.read_bytes()
        bootstrap.install_plugins(data, {**settings, "owner_qq": "99999999"}, ROOT / ".research/extracted-plugins")
        assert proactive_file.read_bytes() == saved_plugin_config
        await bootstrap.initialize(data, settings, "测试大肥鱼人格")
        config = json.loads((data / "cmd_config.json").read_text(encoding="utf-8"))
        assert config["agent_runner"]["config"]["model"]["provider_id"] == "deepseek/deepseek-flash"
        assert config["platform_settings"]["id_whitelist"] == ["qq:FriendMessage:12345678"]
        assert config['platform_settings']['segmented_reply']['enable']
        assert config['provider_settings']['computer_use_runtime'] == 'none'
        assert not config['provider_ltm_settings']['group_message_history_enable']
        group_config = bootstrap.make_config(DEFAULT_CONFIG, {**settings, 'group_ids': ['77777777']}, hash_dashboard_password, hash_md5_dashboard_password)
        assert '77777777' in group_config['platform_settings']['id_whitelist']
        assert group_config['provider_ltm_settings']['active_reply']['enable']
        assert group_config['provider_ltm_settings']['group_message_history_enable']
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
        from upgrade_companion import upgrade
        proactive['friend_settings']['schedule_settings']['max_unanswered_times'] = 2
        proactive_file.write_text(json.dumps(proactive), encoding='utf-8')
        await upgrade(data, settings)
        after = json.loads((data / 'cmd_config.json').read_text(encoding='utf-8'))
        assert after['provider_sources'] == config['provider_sources']
        assert after['admins_id'] == config['admins_id']
        assert after['platform_settings']['id_whitelist'] == config['platform_settings']['id_whitelist']
        assert json.loads(proactive_file.read_text(encoding='utf-8'))['friend_settings']['schedule_settings']['max_unanswered_times'] == 2
        db = SQLiteDatabase(str(data / 'data_v4.db'))
        await db.initialize()
        assert (await db.get_persona_by_id('dafeiyu')).system_prompt == '测试大肥鱼人格'
        legacy = (ROOT / 'bootstrap/persona-legacy-v1.txt').read_text(encoding='utf-8-sig')
        await db.update_persona('dafeiyu', system_prompt=legacy)
        await db.engine.dispose()
        await upgrade(data, settings)
        db = SQLiteDatabase(str(data / 'data_v4.db'))
        await db.initialize()
        assert (await db.get_persona_by_id('dafeiyu')).system_prompt == (ROOT / 'bootstrap/persona.txt').read_text(encoding='utf-8-sig')
        await db.engine.dispose()
        from import_meme_library import import_library
        sample_zip = data / 'personal-test.zip'
        with zipfile.ZipFile(sample_zip, 'w') as bundle:
            bundle.writestr('directories/plugin_data/meme_manager/packs/sample/memes/happy/sample.png', b'test fixture')
            bundle.writestr('config/cmd_config.json', '{"secret":"must-not-import"}')
        assert import_library(sample_zip, data) == 1
        assert not (data / 'config/cmd_config.json').exists()
        assert (data / 'plugin_data/meme_manager/packs/personal-import/memes/happy/sample.png').read_bytes() == b'test fixture'
        try:
            import_library(sample_zip, data)
        except RuntimeError:
            pass
        else:
            raise AssertionError('Existing private meme library was overwritten')
    assert json.dumps(DEFAULT_CONFIG, sort_keys=True) == before
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    assert compose["services"]["astrbot"]["ports"] == ["127.0.0.1:6185:6185"]
    assert compose["services"]["napcat"]["ports"] == ["127.0.0.1:6099:6099"]
    assert not compose["services"]["ollama"].get("ports")
    print("PASS: upstream defaults + password hashes + SQLite persona + bundled plugin configs + restart preservation + YAML")


asyncio.run(main())
