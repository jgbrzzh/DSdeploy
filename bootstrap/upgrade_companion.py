"""Explicit, backup-first upgrade of expression settings; preserve user identities."""
import asyncio
import copy
import json
from pathlib import Path

from bootstrap import install_plugins
from companion_profile import configure_core, configure_plugin


def save(path, value):
    temporary = path.with_suffix('.upgrade.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


async def upgrade(data, settings):
    path = data / 'cmd_config.json'
    if not path.exists():
        raise RuntimeError('Start the deployment once before applying an upgrade.')
    config = json.loads(path.read_text(encoding='utf-8-sig'))
    model = config.get('agent_runner', {}).get('config', {}).get('model', {}).get('provider_id')
    model = model or config.get('provider_settings', {}).get('default_provider_id') or 'deepseek/' + settings['model']
    old_active = copy.deepcopy(config.get('provider_ltm_settings', {}).get('active_reply', {}))
    groups = []
    for value in config.get('platform_settings', {}).get('id_whitelist', []):
        value = str(value)
        if value.isdigit():
            groups.append(value)
        elif ':GroupMessage:' in value:
            groups.append(value.rsplit(':', 1)[1])
    configure_core(config, model, groups)
    config['provider_ltm_settings']['active_reply'] = old_active
    install_plugins(data, settings)
    for name in ['astrbot_plugin_proactive_chat', 'meme_manager']:
        target = data / 'config' / (name + '_config.json')
        plugin = json.loads(target.read_text(encoding='utf-8-sig'))
        prior_max = plugin.get('friend_settings', {}).get('schedule_settings', {}).get('max_unanswered_times')
        configure_plugin(name, plugin, model)
        if name == 'astrbot_plugin_proactive_chat' and prior_max not in (None, 1):
            plugin['friend_settings']['schedule_settings']['max_unanswered_times'] = prior_max
        save(target, plugin)
    from astrbot.core.db.sqlite import SQLiteDatabase
    db = SQLiteDatabase(str(data / 'data_v4.db'))
    await db.initialize()
    try:
        current = await db.get_persona_by_id('dafeiyu')
        legacy = Path(__file__).with_name('persona-legacy-v1.txt').read_text(encoding='utf-8-sig').strip()
        desired = Path(__file__).with_name('persona.txt').read_text(encoding='utf-8-sig')
        if current and current.system_prompt.replace('\r\n', '\n').strip() == legacy.replace('\r\n', '\n'):
            await db.update_persona('dafeiyu', system_prompt=desired)
            print('Unmodified v1.0 default persona upgraded.')
        elif current:
            print('Custom or already upgraded persona preserved.')
    finally:
        await db.engine.dispose()
    save(path, config)
    print('Companion expression upgraded; model keys, account IDs, allowlists and schedules retained.')


if __name__ == '__main__':
    settings = json.loads(Path('/deploy-private/settings.json').read_text(encoding='utf-8-sig'))
    asyncio.run(upgrade(Path('/AstrBot/data'), settings))
