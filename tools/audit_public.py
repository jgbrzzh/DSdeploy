"""Audit allowlisted public sources and nested release archives; report no values."""
import argparse
import io
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

from public_files import ROOT, collect

RULES = {
    'personal Windows profile path': re.compile(r'[A-Za-z]:[\\/]+Users[\\/]+(?!Public\b|Default\b)[^\\/\s"\'<>]+', re.I),
    'machine hostname': re.compile(r'\b(?:LAPTOP|DESKTOP)-[A-Z0-9]{5,}\b', re.I),
    'GitHub credential': re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b'),
    'API credential': re.compile(r'\bsk-[A-Za-z0-9_-]{24,}\b'),
    'private key': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
}
PRIVATE_TOP = {'private', 'data', 'runtime', 'backups', '.research', '.runtime-test', '.publish', '.git'}
issues = []
count = 0


def inspect_bytes(name, content, depth=0, third_party=False):
    global count
    count += 1
    if name.lower().endswith('.zip'):
        if depth > 3:
            issues.append((name, 'excessive nested archives'))
            return
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            if sum(item.file_size for item in archive.infolist()) > 256 * 1024 * 1024:
                issues.append((name, 'unexpectedly large source archive'))
                return
            for item in archive.infolist():
                if item.is_dir():
                    continue
                parts = Path(item.filename).parts
                if '..' in parts or item.filename.startswith(('/', '\\')):
                    issues.append((name, 'unsafe ZIP entry'))
                    continue
                inspect_bytes(name + '!' + item.filename, archive.read(item), depth + 1,
                              third_party or '/vendor/' in ('/' + name.replace('\\', '/')))
        return
    try:
        text = content.decode('utf-8-sig')
    except UnicodeDecodeError:
        return
    for label, pattern in RULES.items():
        for match in pattern.finditer(text):
            if third_party and label == 'personal Windows profile path' and name.endswith('!tests/test_faiss_path_bridge.py'):
                segments = re.split(r'[\\/]+', match.group())
                if len(segments) >= 3 and segments[2] in {'test', '张三'}:
                    continue  # Reviewed synthetic paths in the pinned upstream test.
            # Fixed, repeated example keys in upstream test fixtures are not credentials.
            if label == 'API credential' and len(set(match.group()[3:])) < 5:
                continue
            line = text.count('\n', 0, match.start()) + 1
            issues.append((f'{name}:{line}', label))
    if not third_party:
        for line, value in enumerate(text.splitlines(), 1):
            if re.search(r'[A-Za-z]:[\\/]+Github[\\/]+DSdeploy\b', value, re.I):
                issues.append((f'{name}:{line}', 'local project path'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--archive', action='append', default=[])
    parser.add_argument('--staged', action='store_true')
    parser.add_argument('--tracked', action='store_true')
    args = parser.parse_args()
    files = collect()
    allowed = {path.relative_to(ROOT).as_posix() for path in files}
    if args.staged or args.tracked:
        command = ['git', 'ls-files', '-z'] if args.tracked else ['git', 'diff', '--cached', '--name-only', '--diff-filter=ACMR', '-z']
        names = subprocess.check_output(command, cwd=ROOT).decode('utf-8').split('\0')
        for name in filter(None, names):
            if name not in allowed:
                issues.append((name, 'not in source publication allowlist'))
    for path in files:
        relative = path.relative_to(ROOT).as_posix()
        if relative.split('/')[0] in PRIVATE_TOP or path.is_symlink():
            issues.append((relative, 'private or linked path'))
            continue
        if not path.exists():
            issues.append((relative, 'missing required source file'))
            continue
        inspect_bytes(relative, path.read_bytes())
    for filename in args.archive:
        path = Path(filename)
        with zipfile.ZipFile(path) as archive:
            for item in archive.infolist():
                parts = Path(item.filename).parts
                # The release has one top-level application directory.
                if len(parts) > 1 and parts[1] in PRIVATE_TOP:
                    issues.append((item.filename, 'runtime directory in release'))
        inspect_bytes(path.name, path.read_bytes())
    print(json.dumps({'checked_entries': count, 'findings': [{'file': name, 'reason': reason} for name, reason in issues]}, ensure_ascii=False))
    return 1 if issues else 0


if __name__ == '__main__':
    sys.exit(main())
