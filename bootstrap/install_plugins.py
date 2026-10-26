"""Extract bundled, unmodified upstream sources after SHA-256 verification."""
import hashlib
import importlib.metadata
import json
import sys
import zipfile
from pathlib import Path


def extract(source, destination):
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    for plugin in manifest["plugins"]:
        archive = source / plugin["archive"]
        if hashlib.sha256(archive.read_bytes()).hexdigest() != plugin["sha256"]:
            raise RuntimeError("Bundled plugin checksum mismatch: " + plugin["name"])
        target = destination / plugin["name"]
        target.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive) as bundle:
            for entry in bundle.infolist():
                resolved = (target / entry.filename).resolve()
                if not resolved.is_relative_to(target.resolve()):
                    raise RuntimeError("Unsafe archive path")
            bundle.extractall(target)


if __name__ == "__main__":
    extract(Path(sys.argv[1]), Path(sys.argv[2]))
    if len(sys.argv) > 3:
        # Preserve the actual base image's installed dependencies. Unlike a
        # uv-exported project requirements file, these contain no editable
        # project entries that pip cannot accept in a constraints file.
        pins = sorted({f"{dist.metadata['Name']}=={dist.version}"
                       for dist in importlib.metadata.distributions()
                       if dist.metadata.get("Name")})
        Path(sys.argv[3]).write_text("\n".join(pins) + "\n", encoding="utf-8")
