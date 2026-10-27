"""Configure AstrBot's built-in DeepSeek Search/Fetch; never reuse proxy keys."""
import json
from pathlib import Path
from urllib.parse import urlsplit


def official_key(base, keys):
    if urlsplit(str(base)).hostname != 'api.deepseek.com':
        return ''
    if isinstance(keys, str):
        keys = [keys]
    keys = keys or []
    return next((key for key in keys if isinstance(key, str) and key.strip()), '')


def configure_fresh(config, settings):
    key = settings.get('search_api_key') or official_key(settings.get('api_base', ''), [settings.get('api_key', '')])
    provider = config['provider_settings']
    provider.update(web_search=bool(key), websearch_provider='deepseek',
                    websearch_deepseek_key=[key] if key else [], web_search_link=True)


def enable_existing(config, settings):
    provider = config['provider_settings']
    keys = [key for key in provider.get('websearch_deepseek_key', []) if isinstance(key, str) and key.strip()]
    if not keys:
        current = config.get('agent_runner', {}).get('config', {}).get('model', {}).get('provider_id')
        current = current or provider.get('default_provider_id')
        model = next((p for p in config.get('provider', []) if p.get('id') == current), {})
        source = next((p for p in config.get('provider_sources', [])
                       if p.get('id') == model.get('provider_source_id')), {})
        key = official_key(source.get('api_base', ''), source.get('key', []))
        key = key or settings.get('search_api_key', '')
        if not key:
            raise RuntimeError('No official DeepSeek key available. Set DeepSeek Search API key in AstrBot AI/Web Search first; third-party model keys will not be sent to DeepSeek.')
        keys = [key]
    provider.update(web_search=True, websearch_provider='deepseek',
                    websearch_deepseek_key=keys, web_search_link=True)


if __name__ == '__main__':
    path = Path('/AstrBot/data/cmd_config.json')
    config = json.loads(path.read_text(encoding='utf-8-sig'))
    settings = json.loads(Path('/deploy-private/settings.json').read_text(encoding='utf-8-sig'))
    enable_existing(config, settings)
    temporary = path.with_suffix('.search.tmp')
    temporary.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)
    print('DeepSeek Search and Fetch enabled for this instance. Model, account and other settings retained.')
