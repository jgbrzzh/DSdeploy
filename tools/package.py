"""Create a clean distributable using an explicit allowlist; never package data."""
import hashlib
import json
import zipfile
from pathlib import Path
from public_files import collect

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
DIST.mkdir(exist_ok=True)
files = collect(package=True)
archive = DIST / "QQ大肥鱼一键部署包.zip"
prefix = "QQ大肥鱼一键部署包/"
manifest = []
with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
    for path in files:
        relative = path.relative_to(ROOT).as_posix()
        if path.is_symlink():
            raise RuntimeError("Refusing symlink in package: " + relative)
        data = path.read_bytes()
        bundle.writestr(prefix + relative, data)
        manifest.append({"path": relative, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    bundle.writestr(prefix + "文件校验清单.json", json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"))
with zipfile.ZipFile(archive) as bundle:
    assert bundle.testzip() is None
    for name in bundle.namelist():
        parts = Path(name).parts
        assert not any(part in {"private", "data", "runtime", ".research", "backups", "__pycache__"} for part in parts)
    bundled = json.loads(bundle.read(prefix + "vendor/manifest.json"))
    for plugin in bundled["plugins"]:
        payload = bundle.read(prefix + "vendor/" + plugin["archive"])
        assert hashlib.sha256(payload).hexdigest() == plugin["sha256"]
    resources = json.loads(bundle.read(prefix + 'meme-packs/manifest.json'))
    for pack in resources['packs']:
        for part in pack['archives']:
            assert hashlib.sha256(bundle.read(prefix + 'meme-packs/' + part['file'])).hexdigest() == part['sha256']
checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
(DIST / "QQ大肥鱼一键部署包.zip.sha256").write_text(checksum + "  " + archive.name + "\n", encoding="utf-8")
print(json.dumps({"archive": str(archive), "bytes": archive.stat().st_size,
                  "files": len(files) + 1, "sha256": checksum, "zip_check": "passed"}, ensure_ascii=False))
