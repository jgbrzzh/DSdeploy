"""Exercise the actual Windows launcher against a simulated Docker CLI.

All fixtures live in .research. No containers, installers or API calls run.
"""
import http.server
import json
import os
import shutil
import socketserver
import subprocess
import sys
import tempfile
import threading
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class QuietHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"fixture")

    def log_message(self, *args):
        pass


MOCK = r'''
import json, os, sys
from pathlib import Path
root = Path(os.environ['DSDEPLOY_FIXTURE'])
args = sys.argv[1:]
with (root/'commands.jsonl').open('a',encoding='utf-8') as log:
    log.write(json.dumps(args)+'\n')
if args[0] == 'info':
    print('linux'); sys.exit(0)
if args[:2] == ['image','inspect']:
    canonical=args[2].replace(':latest','')+'@sha256:'+'a'*64
    print(json.dumps([canonical,'docker.m.daocloud.io/'+canonical])); sys.exit(0)
if args[:3] == ['image','ls','-q']:
    if (root/'image-built').exists(): print('fixture-image')
    sys.exit(0)
if args[0] == 'pull': sys.exit(0)
if args[:2] == ['compose','version']: print('2.40.0'); sys.exit(0)
if 'build' in args:
    print('build progress on stderr', file=sys.stderr)
    (root/'image-built').write_text('ok')
if 'show' in args and 'bge-m3' in args and not (root/'model-pulled').exists():
    print('model not found', file=sys.stderr); sys.exit(1)
if 'pull' in args and 'bge-m3' in args:
    print('model progress on stderr', file=sys.stderr)
    (root/'model-pulled').write_text('ok')
if 'run' in args:
    if '/bootstrap/prepare_ollama_dns.py' in args: print('{}'); sys.exit(0)
    if (root/'fail-bootstrap').exists(): sys.exit(42)
    target=root/'data/astrbot/cmd_config.json'
    if not target.exists(): target.write_text('preserve-user-config')
if 'ps' in args and '--services' in args:
    active=root/'active-services'
    print(active.read_text() if active.exists() else '')
for operation in ('up','start','stop'):
    if operation not in args: continue
    active=root/'active-services'
    previous=set(active.read_text().splitlines()) if active.exists() else set()
    targets=set(args[args.index(operation)+1:]) & {'astrbot','napcat','ollama'}
    if operation=='stop': current=previous-targets if targets else set()
    else: current=previous | (targets or {'astrbot','ollama'})
    active.write_text('\n'.join(sorted(current)))
sys.exit(0)
'''


def main():
    (ROOT / '.research').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="launcher-中文 ", dir=ROOT / ".research") as folder:
        root = Path(folder)
        shutil.copy2(ROOT / "Deploy.ps1", root)
        for name in ["compose.yaml", "Dockerfile"]:
            shutil.copy2(ROOT / name, root)
        for directory in ["bootstrap", "vendor"]:
            shutil.copytree(ROOT / directory, root / directory, ignore=shutil.ignore_patterns("__pycache__"))
        (root / "meme-packs").mkdir()
        shutil.copy2(ROOT / 'meme-packs/manifest.json', root / 'meme-packs/manifest.json')
        (root / "private").mkdir()
        settings = dict(owner_qq="12345678", bot_qq="87654321", model="deepseek-flash",
                        api_base="https://api.deepseek.com/v1", api_key="fixture-only",
                        onebot_token="onebot-fixture", napcat_token="napcat-fixture",
                        dashboard_password="Whale!fixture123", jwt_secret="fixture-jwt")
        settings_path = root / "private/settings.json"
        settings_path.write_text(json.dumps(settings), encoding="utf-8")
        mock_bin = root / "mock-bin"
        mock_bin.mkdir()
        (mock_bin / "fake_docker.py").write_text(MOCK, encoding="utf-8")
        (mock_bin / "docker.cmd").write_text('@echo off\r\n"' + sys.executable + '" "%~dp0fake_docker.py" %*\r\n', encoding="utf-8")
        environment = {**os.environ, "PATH": str(mock_bin) + os.pathsep + os.environ["PATH"],
                       "DSDEPLOY_FIXTURE": str(root)}
        environment.pop("PSModulePath", None)  # Match a double-click from cmd, not inherited pwsh 7 modules.

        def run(action, success=True):
            process = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                                      "-File", str(root / "Deploy.ps1"), "-Action", action, "-NoBrowser"],
                                     env=environment, capture_output=True)
            if (process.returncode == 0) != success:
                raise AssertionError(process.stdout.decode("utf-8", errors="replace") + process.stderr.decode("utf-8", errors="replace"))

        # Enforce the location requirement before any image pulls or bootstrap.
        run("Start", success=False)
        commands = (root / "commands.jsonl").read_text(encoding="utf-8")
        assert '"pull"' not in commands
        disk = root / "data/docker-desktop/test.vhdx"
        disk.parent.mkdir(parents=True)
        disk.write_text("fixture only")
        servers = []
        try:
            for port in [6185, 6099]:
                server = socketserver.TCPServer(("127.0.0.1", port), QuietHandler)
                servers.append(server)
                threading.Thread(target=server.serve_forever, daemon=True).start()
            # Images are prepared without requiring any QQ/API settings.
            settings_path.unlink()
            run('PrepareImages')
            assert not settings_path.exists()
            assert not (root / 'data/astrbot/cmd_config.json').exists()
            assert not (root / 'data/napcat/webui.json').exists()
            assert not (root / 'active-services').read_text()
            calls = [json.loads(line) for line in (root / 'commands.jsonl').read_text().splitlines()]
            assert not any('/bootstrap/bootstrap.py' in args for args in calls)
            assert any('pull' in args and 'bge-m3' in args for args in calls)
            assert not any('up' in args and args[-1] != 'ollama' for args in calls)
            settings_path.write_text(json.dumps(settings), encoding='utf-8')
            run('Start', success=False)  # No implicit configuration import.
            (root / 'fail-bootstrap').touch()
            run('InitializeConfig', success=False)
            (root / 'fail-bootstrap').unlink()
            run('InitializeConfig')
            assert not (root / 'active-services').read_text()
            count_before_start = len((root / 'commands.jsonl').read_text().splitlines())
            run('Start')
            config = root / "data/astrbot/cmd_config.json"
            saved = config.read_bytes()
            napcat = root / "data/napcat/onebot11_87654321.json"
            napcat_saved = napcat.read_bytes()
            assert json.loads(napcat_saved)["network"]["websocketClients"][0]["token"] == settings["onebot_token"]
            lock = (root / "compose.lock.json").read_bytes()
            lock_data=json.loads(lock)
            assert isinstance(lock_data['services']['ollama']['image'],str)
            assert lock_data['services']['astrbot']['build']['args']['ASTRBOT_BASE'].startswith('docker.m.daocloud.io/')
            run("Start")
            assert config.read_bytes() == saved
            assert napcat.read_bytes() == napcat_saved
            assert (root / "compose.lock.json").read_bytes() == lock
            calls = [json.loads(line) for line in (root / "commands.jsonl").read_text().splitlines()]
            assert sum('build' in args for args in calls) == 1
            assert sum(args[0] == 'pull' for args in calls) == 3
            start_calls = calls[count_before_start:]
            assert not any('build' in args or args[0] == 'pull' or 'run' in args for args in start_calls)
            assert all('never' in args for args in start_calls if 'up' in args)
            run('PrepareImages')
            assert config.read_bytes() == saved and napcat.read_bytes() == napcat_saved
            assert settings_path.read_text(encoding='utf-8') == json.dumps(settings)
            repeated = [json.loads(line) for line in (root / 'commands.jsonl').read_text().splitlines()]
            assert sum(args[0] == 'pull' for args in repeated) == 3
            assert sum('build' in args for args in repeated) == 1
            run('UpdateImages')
            updated = [json.loads(line) for line in (root / 'commands.jsonl').read_text().splitlines()]
            assert sum(args[0] == 'pull' for args in updated) == 6
            assert config.read_bytes() == saved and napcat.read_bytes() == napcat_saved
            assert list((root / 'backups').glob('镜像锁-*.json'))
            # A changed dependency must stop startup before any build/import/up.
            with (root / 'Dockerfile').open('a', encoding='utf-8') as changed:
                changed.write('\n# changed dependency fixture\n')
            before = len((root / 'commands.jsonl').read_text().splitlines())
            run('Start', success=False)
            rejected = [json.loads(line) for line in (root / 'commands.jsonl').read_text().splitlines()][before:]
            assert not any('build' in args or 'up' in args or 'run' in args or args[0]=='pull' for args in rejected)
            run('PrepareImages')
            assert config.read_bytes() == saved
            run('Start')
            run("Backup")
            assert len(list((root / "backups").glob("*.zip"))) == 1
            with zipfile.ZipFile(next((root / "backups").glob("*.zip"))) as backup:
                assert "data/astrbot/cmd_config.json" in backup.namelist()
                assert not any("docker-desktop" in name for name in backup.namelist())
            calls = [json.loads(line) for line in (root / "commands.jsonl").read_text().splitlines()]
            restarts = [args for args in calls if 'start' in args]
            assert restarts[-1][-3:] == ['start', 'astrbot', 'ollama']
            run('InstallMemePacks')
            assert config.read_bytes() == saved
            run('UpgradeCompanion')
            assert len(list((root / 'backups').glob('陪伴升级前-*.zip'))) == 2
            assert config.read_bytes() == saved
            (root / "fail-bootstrap").touch()
            run('Start')  # Startup no longer invokes bootstrap at all.
            assert config.read_bytes() == saved
            run("Stop")
            assert config.read_bytes() == saved
            assert settings_path.read_text(encoding="utf-8") == json.dumps(settings)
        finally:
            for server in servers:
                server.shutdown()
                server.server_close()
    print("PASS: real PowerShell launcher + Chinese/spaced paths + disk guard + independent image/config/start stages + refresh + preservation + backup + failed import")


if __name__ == "__main__":
    main()
