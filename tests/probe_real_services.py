"""Probe only this task's disposable deployment; never print credentials."""
import hashlib
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEST = ROOT / '.runtime-test'
settings = json.loads((TEST / 'package/private/settings.json').read_text(encoding='utf-8'))


def request(path, body=None, token=None):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request('http://127.0.0.1:6185' + path,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers=headers)
    with urllib.request.urlopen(req, timeout=180) as response:
        return json.load(response)


result = {'panels': {}, 'login': False}
for url in ['http://127.0.0.1:6185/', 'http://127.0.0.1:6099/webui']:
    with urllib.request.urlopen(url, timeout=15) as response:
        result['panels'][url] = {'http': response.status, 'html_bytes': len(response.read())}
token = None
for path in ['/api/auth/login', '/api/login']:
    for password in [settings['dashboard_password'], hashlib.md5(settings['dashboard_password'].encode()).hexdigest()]:
        try:
            response = request(path, {'username': 'astrbot', 'password': password})
        except urllib.error.HTTPError as error:
            if error.code == 404:
                break
            continue
        data = response.get('data') or {}
        token = (data.get('token') or data.get('access_token') or data.get('jwt_token')) if isinstance(data, dict) else None
        if token:
            result['login'] = True
            result['login_endpoint'] = path
            break
        time.sleep(1)
    if token:
        break
if token:
    try:
        memory = {'content': '测试记忆：主人喜欢茉莉花茶，验收编号 DSDEPLOY-20261026。',
                  'session_id': 'qq:FriendMessage:12345678', 'persona_id': 'dafeiyu', 'importance': 0.8}
        result['memory_import'] = request('/api/plug/astrbot_plugin_livingmemory/page/memories/import',
                                          {'format': 'json', 'content': json.dumps([memory], ensure_ascii=False),
                                           'dry_run': False, 'duplicate_strategy': 'skip'}, token)
    except Exception as error:
        result['memory_import'] = {'error': str(error)}
    for path in ['/api/plug/astrbot_plugin_livingmemory/page/stats', '/api/plug/astrbot_plugin_livingmemory/page/recall/test']:
        try:
            body = {'query': '主人喜欢喝什么茶？DSDEPLOY-20261026', 'k': 1, 'session_id': 'qq:FriendMessage:12345678'} if path.endswith('/test') else None
            response = request(path, body, token)
            result[path] = response
        except Exception as error:
            result[path] = {'error': str(error)}
output = TEST / 'evidence/service-probe.json'
output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(result, ensure_ascii=False))
