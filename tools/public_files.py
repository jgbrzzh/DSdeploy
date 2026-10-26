"""Explicit publication allowlists shared by packaging and privacy checks."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMANDS = ['一键启动.cmd', '一键停止.cmd', '查看状态.cmd', '查看日志.cmd',
            '备份数据.cmd', '环境检查.cmd', '安装Docker.cmd', '下载镜像包.cmd']
PACKAGE_ROOTS = ['Deploy.ps1', 'Dockerfile', 'compose.yaml', '.dockerignore',
                 'README.md', 'LICENSE', 'NOTICE.md', 'VERSION', *COMMANDS]
SOURCE_ROOTS = [*PACKAGE_ROOTS, '.gitignore', '.gitattributes']


def collect(package=False):
    paths = [ROOT / name for name in (PACKAGE_ROOTS if package else SOURCE_ROOTS)]
    groups = [('bootstrap', {'.py', '.txt'}), ('docs', {'.md', '.json', '.jsonl', '.txt'}),
              ('offline', {'.md'}), ('vendor', {'.md', '.json', '.zip'})]
    if not package:
        groups += [('tests', {'.py', '.sh', '.txt'}), ('tools', {'.py'}), ('.github', {'.yml', '.yaml', '.md'})]
    for directory, suffixes in groups:
        base = ROOT / directory
        if not base.exists():
            continue
        paths.extend(path for path in base.rglob('*')
                     if path.is_file() and path.suffix in suffixes
                     and '__pycache__' not in path.parts)
    return sorted(set(paths), key=lambda path: path.relative_to(ROOT).as_posix())
