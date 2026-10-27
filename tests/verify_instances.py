"""Two directories receive different identities; old/copy roots cannot be targeted."""
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
environment = dict(os.environ)
environment.pop('PSModulePath', None)


def run(root, action, *extra, success=True):
    result = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                             '-File', str(root / 'Deploy.ps1'), '-Action', action, *extra],
                            env=environment, capture_output=True)
    assert (result.returncode == 0) == success, result.stdout.decode('utf-8', errors='replace')


with tempfile.TemporaryDirectory(prefix='instances-', dir=ROOT / '.research') as folder:
    roots = [Path(folder) / name for name in ['old-v1.0', 'new-one', 'new-two', 'copied']]
    for root in roots:
        (root / 'bootstrap').mkdir(parents=True)
        shutil.copy2(ROOT / 'Deploy.ps1', root)
        shutil.copy2(ROOT / 'bootstrap/instance.ps1', root / 'bootstrap/instance.ps1')
    old, first, second, copied = roots
    (old / 'data/astrbot').mkdir(parents=True)
    config = old / 'data/astrbot/cmd_config.json'
    config.write_text('old-version-must-stay')
    run(old, 'Stop', success=False)  # New launcher must not operate a legacy project.
    assert config.read_text(encoding='utf-8') == 'old-version-must-stay'
    assert not (old / 'private/instance.json').exists()
    run(first, 'ConfigureInstance')
    run(second, 'ConfigureInstance')
    a = json.loads((first / 'private/instance.json').read_text(encoding='utf-8'))
    b = json.loads((second / 'private/instance.json').read_text(encoding='utf-8'))
    assert a['project'] != b['project'] and a['image'] != b['image']
    assert {a['astrbot_port'], a['napcat_port']}.isdisjoint({6185, 6099})
    assert {b['astrbot_port'], b['napcat_port']}.isdisjoint({6185, 6099})
    assert a['docker_mode'] == b['docker_mode'] == 'shared'
    run(first, 'ConfigureInstance')
    assert json.loads((first / 'private/instance.json').read_text(encoding='utf-8')) == a
    (copied / 'private').mkdir()
    shutil.copy2(first / 'private/instance.json', copied / 'private/instance.json')
    run(copied, 'Stop', success=False)  # A copied identity cannot stop the original.
    assert config.read_text(encoding='utf-8') == 'old-version-must-stay'
print('PASS: independent directory identities/images/ports + legacy guard + copied identity guard')
