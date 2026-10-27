"""Apply only declarative companion settings, never backup runtime identities."""
import copy
import json
from pathlib import Path

PROFILE_PATH = Path(__file__).with_name('companion_profile.json')


def merge(target, updates):
    for key, value in updates.items():
        if isinstance(value, dict):
            if not isinstance(target.get(key), dict):
                target[key] = {}
            merge(target[key], value)
        else:
            target[key] = copy.deepcopy(value)
    return target


def load():
    return json.loads(PROFILE_PATH.read_text(encoding='utf-8-sig'))


def configure_core(config, model_id, groups=()):
    merge(config, load()['core'])
    config['provider_settings']['default_image_caption_provider_id'] = model_id
    ltm = config['provider_ltm_settings']
    ltm['group_icl_enable'] = bool(groups)
    ltm['group_message_history_enable'] = bool(groups)
    ltm['image_caption'] = True
    ltm['image_caption_provider_id'] = model_id
    # Never activate 100% group auto-replies on an unspecified public audience.
    ltm['active_reply'].update(enable=bool(groups), possibility_reply=0.15, whitelist=list(groups))
    return config


def configure_plugin(name, config, model_id):
    merge(config, load()['plugins'].get(name, {}))
    if name == 'meme_manager':
        config['generation']['emotion']['llm']['provider_id'] = model_id
        config['semantic']['embedding_provider_id'] = 'bge_m3_local'
        config['semantic']['vision_provider_id'] = model_id
    return config
