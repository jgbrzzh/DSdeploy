"""Targeted Linux symlink regression. Does not start Docker or access user data."""
import importlib.util
import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('copy_ollama', ROOT / 'bootstrap/copy_ollama.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def main():
    (ROOT / '.research').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='ollama-link-', dir=ROOT / '.research') as folder:
        root = Path(folder)
        source, target = root / 'source', root / 'target'
        manifest = source / 'models/manifests/registry.ollama.ai/library/bge-m3/latest'
        manifest.parent.mkdir(parents=True)
        content = b'{"schemaVersion":2,"layers":[{"digest":"fixture-model"}]}\n'
        manifest.write_bytes(content)
        alias = source / 'models/manifests-v2/ollama.com/library/bge-m3/latest'
        alias.parent.mkdir(parents=True)
        alias.symlink_to('../../../../manifests/registry.ollama.ai/library/bge-m3/latest')
        absolute = alias.with_name('absolute')
        absolute.symlink_to(manifest.resolve())
        blob = source / 'models/blobs/fixture-model'
        blob.parent.mkdir()
        blob.write_bytes(b'fixture model data')
        report = root / 'files.json'
        module.copy_ollama(source, target, report)
        copied = target / alias.relative_to(source)
        assert copied.read_bytes() == content and not copied.is_symlink()
        assert (target / absolute.relative_to(source)).read_bytes() == content
        assert alias.is_symlink() and alias.read_bytes() == content
        assert any(e.get('materialized_link') for e in json.loads(report.read_text(encoding='utf-8')))
        for kind in ('outside', 'directory', 'dangling', 'loop'):
            link = source / ('unsafe-' + kind)
            if kind == 'outside':
                outside = root / 'outside.txt'
                outside.write_text('must not copy', encoding='utf-8')
                link.symlink_to(outside)
            elif kind == 'directory':
                link.symlink_to(manifest.parent, target_is_directory=True)
            elif kind == 'dangling':
                link.symlink_to(source / 'missing')
            else:
                link.symlink_to(link)
            try:
                try:
                    module.copy_ollama(source, root / ('rejected-' + kind), report)
                except (RuntimeError, OSError):
                    pass
                else:
                    raise AssertionError('unsafe link accepted: ' + kind)
            finally:
                link.unlink()
        print('PASS: exact manifests-v2 bge-m3/latest relative link, absolute in-tree link, regular-file materialization; outside/directory/dangling/loop rejection; source untouched')


if __name__ == '__main__':
    main()
