"""Verify bundled public images, idempotent import and existing user choices."""
import hashlib
import importlib
import types
import json
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'bootstrap'))
from install_meme_packs import install

source = ROOT / 'meme-packs'
manifest = json.loads((source / 'manifest.json').read_text(encoding='utf-8'))
assert [p['images'] for p in manifest['packs']] == [138, 101]
for pack in manifest['packs']:
    count = 0
    for part in pack['archives']:
        archive = source / part['file']
        assert hashlib.sha256(archive.read_bytes()).hexdigest() == part['sha256']
        with zipfile.ZipFile(archive) as bundle:
            assert bundle.testzip() is None
            count += sum(n.startswith('memes/') and Path(n).suffix.lower() in
                         {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp'} for n in bundle.namelist())
    assert count == pack['images']

(ROOT / '.research').mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(prefix='bundled-memes-', dir=ROOT / '.research') as temporary:
    data = Path(temporary)
    assert all(p['status'] == 'installed' for p in install(source, data))
    base = data / 'plugin_data/meme_manager'
    registry = json.loads((base / 'registry.json').read_text())
    assert len(registry['installed_packs']) == 2
    # Exercise the pinned plugin's real multi-pack resolver with fixture paths.
    plugin = ROOT / '.research/extracted-plugins/meme_manager'
    for name, relative in [('pack_check', ''), ('pack_check.backend', 'backend'),
                           ('pack_check.backend.packs', 'backend/packs'),
                           ('pack_check.backend.semantic', 'backend/semantic')]:
        module = types.ModuleType(name)
        module.__path__ = [str(plugin / relative)]
        sys.modules[name] = module
    config = types.ModuleType('pack_check.config')
    config.DEFAULT_CATEGORY_DESCRIPTIONS = {}
    config.DEFAULT_PACK_ID = 'builtin-default'
    config.PACKS_DIR = base / 'packs'
    config.REGISTRY_PATH = base / 'registry.json'
    config.SELECTION_RULES_PATH = base / 'selection_rules.json'
    sys.modules[config.__name__] = config
    resolver = importlib.import_module('pack_check.backend.packs.resolver')
    context = resolver.resolve_pack_context()
    assert context['pack_ids'] == [p['id'] for p in manifest['packs']]
    assert 'happy' in context['category_mapping']
    assert all(path.exists() for path in context['pack_dirs'].values())
    rules = base / 'selection_rules.json'
    assert json.loads(rules.read_text())['rules'][0]['pack_ids'] == [p['id'] for p in manifest['packs']]
    # Local edits and a user's selection must survive subsequent installs.
    edited = base / 'packs/deepseek-girl-pack/keep-my-note.txt'
    edited.write_text('local customization')
    custom = {'schema_version': 1, 'rules': [{'id': 'default', 'scope': 'default', 'pack_id': 'wuwa-phoebe-pack'}]}
    rules.write_text(json.dumps(custom))
    assert all(p['status'] == 'preserved' for p in install(source, data))
    assert edited.read_text() == 'local customization'
    assert json.loads(rules.read_text()) == custom
    assert len(json.loads((base / 'registry.json').read_text())['installed_packs']) == 2
    # A corrupt public archive must fail before creating a pack.
    invalid = data / 'invalid-source'
    invalid.mkdir()
    (invalid / 'bad.zip').write_bytes(b'bad')
    (invalid / 'manifest.json').write_text(json.dumps({'packs': [{
        'id': 'test-pack', 'archives': [{'file': 'bad.zip', 'sha256': '0' * 64}]}]}))
    try:
        install(invalid, data)
    except RuntimeError:
        pass
    else:
        raise AssertionError('Corrupt archive accepted')
    assert not (base / 'packs/test-pack').exists()
print('PASS: 239 public images + checksums + two-pack import + upstream resolver + repeat preservation + checksum rejection')
