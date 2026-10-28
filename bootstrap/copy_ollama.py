"""Copy Ollama data in Linux; materialize in-tree file links for Windows copying.

Run with the source mounted read-only at its original /root/.ollama location.
No Ollama process or model downloads run here.
"""
import hashlib
import json
import shutil
from pathlib import Path


def copy_ollama(source, destination, report):
    source = Path(source).resolve(strict=True)
    destination = Path(destination)
    records = []

    def copy_directory(directory, relative):
        target_dir = destination / relative
        target_dir.mkdir(parents=True, exist_ok=True)
        for entry in sorted(directory.iterdir()):
            child_relative = relative / entry.name
            actual = entry
            linked = entry.is_symlink()
            if linked:
                actual = entry.resolve(strict=True)
                try:
                    actual.relative_to(source)
                except ValueError:
                    raise RuntimeError(f'Ollama link escapes its data directory: {child_relative}') from None
                if not actual.is_file():
                    raise RuntimeError(f'Ollama directory links are not supported: {child_relative}')
            if actual.is_dir():
                copy_directory(actual, child_relative)
            elif actual.is_file():
                target = destination / child_relative
                shutil.copyfile(actual, target)
                digest = hashlib.sha256()
                with target.open('rb') as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b''):
                        digest.update(block)
                if actual.stat().st_size != target.stat().st_size:
                    raise RuntimeError(f'Ollama copy size mismatch: {child_relative}')
                record = dict(path='data/ollama/' + child_relative.as_posix(),
                              bytes=target.stat().st_size, sha256=digest.hexdigest().upper())
                if linked:
                    record['materialized_link'] = True
                records.append(record)
            else:
                raise RuntimeError(f'Unsupported Ollama file: {child_relative}')

    copy_directory(source, Path())
    Path(report).write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    copy_ollama('/root/.ollama', '/migration-target', '/migration-report/files.json')
