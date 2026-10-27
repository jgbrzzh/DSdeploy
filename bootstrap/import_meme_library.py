"""Locally import only meme images from a personal backup, never chats or keys."""
import json
import stat
import zipfile
from pathlib import Path, PurePosixPath

ALLOWED = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp'}
PREFIX = 'directories/plugin_data/meme_manager/'


def import_library(archive, data):
    root = data / 'plugin_data/meme_manager'
    if any(p.is_file() and p.suffix.lower() in ALLOWED for p in (root / 'packs').rglob('*')):
        raise RuntimeError('An existing meme image library was found; import through the plugin UI to merge safely.')
    pack = root / 'packs/personal-import'
    if pack.exists():
        raise RuntimeError('A prior personal-import pack exists. It will not be overwritten.')
    with zipfile.ZipFile(archive) as source:
        descriptions = {}
        for item in source.infolist():
            if item.filename.startswith(PREFIX + 'packs/') and item.filename.endswith('/manifest.json'):
                try:
                    manifest = json.loads(source.read(item).decode('utf-8-sig'))
                    for category, details in manifest.get('categories', {}).items():
                        description = details.get('description', '') if isinstance(details, dict) else str(details)
                        descriptions[category] = str(description)[:1000]
                except (ValueError, UnicodeError):
                    continue
        paths = [item for item in source.infolist() if item.filename.startswith(PREFIX + 'packs/')
                 and '/memes/' in item.filename and not item.is_dir()
                 and Path(item.filename).suffix.lower() in ALLOWED]
        if not paths:
            raise RuntimeError('No compatible meme pack images were found.')
        count = 0
        categories = {}
        for item in paths:
            parts = PurePosixPath(item.filename).parts
            if '..' in parts or item.filename.startswith('/') or stat.S_ISLNK(item.external_attr >> 16):
                raise RuntimeError('Unsafe archive entry')
            index = parts.index('memes')
            relative = PurePosixPath(*parts[index + 1:])
            if len(relative.parts) < 2:
                continue
            category = relative.parts[0]
            destination = pack / 'memes' / Path(*relative.parts)
            if not destination.resolve().is_relative_to(pack.resolve()):
                raise RuntimeError('Image destination escaped import directory')
            if destination.exists():
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(source.read(item))
            categories[category] = {'description': descriptions.get(category) or category}
            count += 1
        if count == 0:
            raise RuntimeError('No categorized images could be imported')
    pack.mkdir(parents=True, exist_ok=True)
    manifest = {'schema_version': 1, 'id': 'personal-import', 'name': 'Personal imported memes',
                'version': '1.0.0', 'description': 'Private local images, not distributed by DSdeploy',
                'categories': categories}
    registry = {'schema_version': 1, 'installed_packs': [{'id': 'personal-import', 'name': manifest['name'], 'version': '1.0.0', 'enabled': True}]}
    rules = {'schema_version': 1, 'rules': [{'id': 'default', 'scope': 'default', 'pack_id': 'personal-import'}]}
    for path, value in [(pack / 'manifest.json', manifest), (root / 'registry.json', registry),
                        (root / 'selection_rules.json', rules)]:
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    return count


if __name__ == '__main__':
    count = import_library(Path('/deploy-private/meme-import.zip'), Path('/AstrBot/data'))
    print(f'Imported {count} private meme images. No conversations, IDs, credentials or indexes restored.')
