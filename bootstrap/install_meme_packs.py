"""Install bundled public packs independently of images and private backups."""
import hashlib
import json
import os
import re
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath


def read_json(path, default):
    return json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else default


def save(path, value):
    temporary = path.with_suffix('.dsdeploy.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def regular_tree(path):
    for item in [path, *path.parents]:
        if item.is_symlink() or getattr(item, 'is_junction', lambda: False)():
            raise RuntimeError('Linked destination refused')
    if path.exists():
        for item in path.rglob('*'):
            if item.is_symlink() or getattr(item, 'is_junction', lambda: False)():
                raise RuntimeError('Linked destination refused')


def install(source, data):
    manifest = read_json(source / 'manifest.json', {})
    root = data / 'plugin_data/meme_manager'
    regular_tree(root)
    registry = read_json(root / 'registry.json', {'schema_version': 1, 'installed_packs': []})
    if not isinstance(registry.get('installed_packs'), list):
        raise RuntimeError('Invalid existing pack registry; left unchanged')
    rules = root / 'selection_rules.json'
    results = []
    for pack in manifest['packs']:
        pack_id = pack['id']
        if not re.fullmatch(r'[a-z0-9_-]+', pack_id):
            raise RuntimeError('Invalid bundled pack ID')
        target = root / 'packs' / pack_id
        if not target.exists():
            archives = []
            for part in pack['archives']:
                archive = source / part['file']
                if archive.parent.resolve() != source.resolve():
                    raise RuntimeError('Unsafe bundled archive filename')
                if hashlib.sha256(archive.read_bytes()).hexdigest() != part['sha256']:
                    raise RuntimeError('Bundled meme checksum mismatch: ' + pack_id)
                with zipfile.ZipFile(archive) as bundle:
                    for entry in bundle.infolist():
                        name = PurePosixPath(entry.filename)
                        if (name.is_absolute() or '..' in name.parts or '\\' in entry.filename
                                or ':' in entry.filename or stat.S_ISLNK(entry.external_attr >> 16)):
                            raise RuntimeError('Unsafe bundled archive entry')
                archives.append(archive)
            target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix='.dsdeploy-pack-', dir=target.parent) as temporary:
                staged = Path(temporary) / pack_id
                staged.mkdir()
                for archive in archives:
                    with zipfile.ZipFile(archive) as bundle:
                        bundle.extractall(staged)
                info = read_json(staged / 'manifest.json', {})
                if info.get('id') != pack_id:
                    raise RuntimeError('Pack manifest ID mismatch')
                # Upstream manifests contain UTF-8 BOM; the pinned resolver
                # reads plain UTF-8 JSON. Normalize only the runtime manifest.
                save(staged / 'manifest.json', info)
                os.replace(staged, target)
            status = 'installed'
        else:
            info = read_json(target / 'manifest.json', {})
            if info.get('id') != pack_id:
                raise RuntimeError('Existing pack has an unexpected manifest; preserved')
            status = 'preserved'
        if not any(item.get('id') == pack_id for item in registry['installed_packs']):
            registry['installed_packs'].append({'id': pack_id, 'name': info['name'],
                                               'version': info['version'], 'enabled': True})
        results.append({'id': pack_id, 'status': status})
    save(root / 'registry.json', registry)
    # New installations use both packs; existing user/session choices stay intact.
    if not rules.exists():
        save(rules, {'schema_version': 1, 'rules': [{'id': 'default', 'scope': 'default',
              'pack_ids': [p['id'] for p in manifest['packs']]}]})
    return results


if __name__ == '__main__':
    print(json.dumps(install(Path('/deploy-meme-packs'), Path('/AstrBot/data'))))
