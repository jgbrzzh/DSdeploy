"""Runs inside the selected AstrBot image, before starting either service."""
import asyncio
import copy
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "/AstrBot")


def make_config(defaults, settings, password_hash, md5_hash):
    config = copy.deepcopy(defaults)
    model_id = "deepseek/" + settings["model"]
    config["admins_id"] = [settings["owner_qq"]]
    config["wake_prefix"] = ["/", "大肥鱼"]
    config["timezone"] = "Asia/Shanghai"
    config["platform"] = [{
        "id": "qq", "type": "aiocqhttp", "enable": True,
        "ws_reverse_host": "0.0.0.0", "ws_reverse_port": 6199,
        "ws_reverse_token": settings["onebot_token"],
    }]
    config["platform_settings"].update({
        "enable_id_white_list": True,
        "id_whitelist": ["qq:FriendMessage:" + settings["owner_qq"]],
        "wl_ignore_admin_on_friend": True, "wl_ignore_admin_on_group": False,
        "friend_message_needs_wake_prefix": False,
        "ignore_bot_self_message": True,
    })
    config["provider_sources"] = [{
        "id": "deepseek", "provider": "openai", "type": "openai_chat_completion",
        "provider_type": "chat_completion", "enable": True,
        "key": [settings["api_key"]], "api_base": settings["api_base"],
        "timeout": 120, "proxy": "", "custom_headers": {},
    }]
    config["provider"] = [{
        "id": model_id, "provider_source_id": "deepseek", "enable": True,
        "type": "openai_chat_completion", "provider_type": "chat_completion",
        "model": settings["model"], "modalities": ["text", "image"],
    }]
    config["provider"].append({
        "id": "bge_m3_local", "type": "ollama_embedding", "provider": "ollama",
        "provider_type": "embedding", "enable": True,
        "embedding_api_base": "http://ollama:11434", "embedding_model": "bge-m3",
        "embedding_dimensions": 1024, "timeout": 180, "proxy": "",
    })
    if "agent_runner" in config:
        runner = config["agent_runner"]
        if runner.get("runner_type") != "local":
            raise RuntimeError("Unsupported default runner; initialization stopped.")
        runner["config"]["model"]["provider_id"] = model_id
        runner["config"]["model"]["request_max_retries"] = 2
        runner["config"]["persona"]["persona_id"] = "dafeiyu"
    else:
        # AstrBot 4.x before the Agent Runner config migration.
        config["provider_settings"]["default_provider_id"] = model_id
        config["provider_settings"]["default_personality"] = "dafeiyu"
    config["dashboard"].update({
        "host": "0.0.0.0", "username": "astrbot",
        "password": md5_hash(settings["dashboard_password"]),
        "pbkdf2_password": password_hash(settings["dashboard_password"]),
        "password_storage_upgraded": True, "password_change_required": False,
        "jwt_secret": settings["jwt_secret"],
    })
    return config


def schema_defaults(schema):
    result = {}
    for key, item in schema.items():
        if item.get("type") == "object":
            result[key] = schema_defaults(item.get("items", {}))
        elif "default" in item:
            result[key] = copy.deepcopy(item["default"])
    return result


def install_plugins(data, settings, source=Path("/opt/dsdeploy-plugins")):
    umo = "qq:FriendMessage:" + settings["owner_qq"]
    configs = data / "config"
    configs.mkdir(parents=True, exist_ok=True)
    for name in ["astrbot_plugin_livingmemory", "astrbot_plugin_proactive_chat"]:
        plugin_source = source / name
        target = data / "plugins" / name
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            staging = target.with_name(target.name + ".installing")
            if staging.exists():
                shutil.rmtree(staging)
            shutil.copytree(plugin_source, staging)
            os.replace(staging, target)
        config_file = configs / (name + "_config.json")
        if config_file.exists():
            continue
        config = schema_defaults(json.loads((target / "_conf_schema.json").read_text(encoding="utf-8-sig")))
        if name.endswith("livingmemory"):
            config["provider_settings"].update({"embedding_provider_id": "bge_m3_local", "llm_provider_id": "deepseek/" + settings["model"]})
            config["filtering_settings"].update({"memory_scope_mode": "session", "use_persona_filtering": True, "use_session_filtering": True})
            config["access_control"].update({"whitelist_enabled": True, "allowed_ids": umo})
            config["session_manager"]["enable_full_group_capture"] = False
            config["reflection_engine"]["summary_trigger_rounds"] = 10
            config["agent_tools"].update({"enable_recall_tool": True, "enable_memorize_tool": True})
        else:
            friend = config["friend_settings"]
            friend.update({"enable": True, "session_list": [umo]})
            friend["auto_trigger_settings"].update({"enable_auto_trigger": True, "auto_trigger_after_minutes": 60})
            friend["schedule_settings"].update({"min_interval_minutes": 120, "max_interval_minutes": 240, "quiet_hours": "23-8", "max_unanswered_times": 1})
            friend["tts_settings"]["enable_tts"] = False
            friend["proactive_prompt"] = (
                "现在是 {{current_time}}。请按大肥鱼人格自然地找对方聊一句，结合最近话题和可见的长期记忆。"
                "可以关心近况或分享一个轻松想法，不编造对方经历，不催促回复，不用内疚或失落施压。"
                "只输出要发送的简短中文消息。"
            )
            config["group_settings"]["enable"] = False
            config["web_admin"]["enabled"] = False
            config["notification_settings"]["enabled"] = False
            config["telemetry_config"]["enabled"] = False
        temporary = config_file.with_suffix(".tmp")
        temporary.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, config_file)


async def initialize(data, settings, persona):
    target = data / "cmd_config.json"
    if target.exists():
        print("Existing AstrBot configuration preserved.")
        return
    # Importing astrbot.core itself creates its default config. Keep that side
    # effect off the real data directory until initialization fully succeeds.
    original_root = os.environ.get("ASTRBOT_ROOT")
    with tempfile.TemporaryDirectory(prefix="dsdeploy-import-") as staging:
        os.environ["ASTRBOT_ROOT"] = staging
        try:
            from astrbot.core.config.default import DEFAULT_CONFIG
            from astrbot.core.db.sqlite import SQLiteDatabase
            from astrbot.core.utils.auth_password import hash_dashboard_password, hash_md5_dashboard_password
        finally:
            if original_root is None:
                os.environ.pop("ASTRBOT_ROOT", None)
            else:
                os.environ["ASTRBOT_ROOT"] = original_root

    config = make_config(DEFAULT_CONFIG, settings, hash_dashboard_password, hash_md5_dashboard_password)
    db = SQLiteDatabase(str(data / "data_v4.db"))
    await db.initialize()
    try:
        if not await db.get_persona_by_id("dafeiyu"):
            await db.insert_persona(persona_id="dafeiyu", system_prompt=persona,
                                   tools=["recall_long_term_memory", "memorize_long_term_memory"], skills=[])
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, target)
    finally:
        await db.engine.dispose()
    print("AstrBot model, QQ adapter and dafeiyu persona initialized.")


if __name__ == "__main__":
    settings = json.loads(Path("/deploy-private/settings.json").read_text(encoding="utf-8-sig"))
    persona = Path("/bootstrap/persona.txt").read_text(encoding="utf-8-sig")
    install_plugins(Path("/AstrBot/data"), settings)
    asyncio.run(initialize(Path("/AstrBot/data"), settings, persona))
