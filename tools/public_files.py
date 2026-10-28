"""Explicit publication allowlists shared by packaging and privacy checks."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMANDS = ['一键启动.cmd', '一键停止.cmd', '查看状态.cmd', '查看日志.cmd',
            '备份数据.cmd', '环境检查.cmd', '安装Docker.cmd', '下载镜像包.cmd',
            '升级陪伴配置.cmd', '导入我的表情库.cmd',
            '下载准备镜像.cmd', '更新镜像.cmd', '导入初始配置.cmd', '导入内置表情库.cmd', '实例设置.cmd', '配置DS联网搜索.cmd',
            '修复NapCat DNS.cmd', '恢复NapCat DNS.cmd', '一键迁移旧版本.cmd', '回退版本迁移.cmd']
PACKAGE_ROOTS = ['Deploy.ps1', 'Dockerfile', 'compose.yaml', '.dockerignore',
                 'README.md', '先看这里.md', 'LICENSE', 'NOTICE.md', 'VERSION', *COMMANDS]
SOURCE_ROOTS = [*PACKAGE_ROOTS, '.gitignore', '.gitattributes']


def collect(package=False):
    paths = [ROOT / name for name in (PACKAGE_ROOTS if package else SOURCE_ROOTS)]
    groups = [('bootstrap', {'.py', '.ps1', '.txt', '.json'}), ('docs', {'.md', '.json', '.jsonl', '.txt'}),
              ('offline', {'.md'}), ('meme-packs', {'.md', '.json', '.zip'}), ('vendor', {'.md', '.json', '.zip'})]
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
