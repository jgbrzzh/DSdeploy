"""Opt-in real Docker check of namespace, mounts, ports and stop isolation.

Uses an explicitly named disposable WSL distro and an existing test image.
Runs Python HTTP fixtures, not QQ login or a real chat model.
"""
import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / '.research/isolation-real'
DISTRO = os.environ.get('DSDEPLOY_TEST_DISTRO')
if DISTRO != 'DSdeploy-Test-20261026':
    raise SystemExit('Explicitly select the disposable DSdeploy test distro.')


def docker(*args, values=None):
    environment = ['env', *[key + '=' + str(value) for key, value in (values or {}).items()]]
    output = subprocess.check_output(['wsl.exe', '-d', DISTRO, '-u', 'root', '--exec',
                                      *environment, 'docker', *args], stderr=subprocess.STDOUT)
    return output.decode('utf-8').strip()


def linux(path):
    return '/mnt/' + path.drive[0].lower() + '/' + str(path)[3:].replace('\\', '/')


instances = []
old_image = docker('image', 'inspect', 'dsdeploy-astrbot:companion-1.1-test', '--format', '{{.Id}}')
for index, name in enumerate(['a', 'b']):
    root = BASE / name
    for folder in ['data/astrbot', 'private', 'bootstrap', 'meme-packs']:
        (root / folder).mkdir(parents=True, exist_ok=True)
    (root / 'data/astrbot/index.html').write_text('isolated-instance-' + name)
    (root / 'compose.yaml').write_bytes((ROOT / 'compose.yaml').read_bytes())
    override = {'services': {'astrbot': {'entrypoint': ['python', '-m', 'http.server', '6185',
                  '--bind', '0.0.0.0', '--directory', '/AstrBot/data'], 'command': []}}}
    (root / 'probe.json').write_text(json.dumps(override))
    project = 'dsdeploy-isolation-probe-' + name
    image = project + ':local'
    docker('tag', 'dsdeploy-astrbot:companion-1.1-test', image)
    values = dict(DSDEPLOY_PROJECT=project, DSDEPLOY_ASTRBOT_IMAGE=image,
                  DSDEPLOY_ASTRBOT_PORT=28185 + index, DSDEPLOY_NAPCAT_PORT=28099 + index)
    args = ['compose', '--project-name', project, '--project-directory', linux(root),
            '-f', linux(root / 'compose.yaml'), '-f', linux(root / 'probe.json')]
    instances.append((name, root, values, args))


def compose(instance, *args):
    return docker(*instance[3], *args, values=instance[2])


def response(instance):
    url = 'http://127.0.0.1:' + str(instance[2]['DSDEPLOY_ASTRBOT_PORT'])
    for _ in range(30):
        try:
            return urllib.request.urlopen(url, timeout=2).read().decode()
        except OSError:
            time.sleep(1)
    raise RuntimeError('Fixture panel not reachable')


try:
    for item in instances:
        compose(item, 'up', '-d', '--no-build', '--pull', 'never', '--no-deps', 'astrbot')
        assert response(item) == 'isolated-instance-' + item[0]
    details = [json.loads(docker('inspect', compose(item, 'ps', '-q', 'astrbot')))[0] for item in instances]
    assert set(details[0]['NetworkSettings']['Networks']).isdisjoint(details[1]['NetworkSettings']['Networks'])
    assert details[0]['Config']['Image'] != details[1]['Config']['Image']
    mounts = [{m['Destination']: m['Source'] for m in item['Mounts']} for item in details]
    assert mounts[0]['/AstrBot/data'] != mounts[1]['/AstrBot/data']
    compose(instances[0], 'stop')
    assert response(instances[1]) == 'isolated-instance-b'
    assert old_image == docker('image', 'inspect', 'dsdeploy-astrbot:companion-1.1-test', '--format', '{{.Id}}')
    result = {'date': '2026-10-27', 'real_docker': True, 'two_simultaneous_http_fixtures': True,
              'separate_images_networks_mounts_ports': True, 'stop_one_other_stays_available': True,
              'original_image_unchanged': True, 'real_qq_or_model_test': False}
    (BASE / 'result.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result))
finally:
    for item in instances:
        compose(item, 'stop')
