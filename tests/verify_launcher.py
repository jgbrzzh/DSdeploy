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
if 'ps' in args and '--services' in args: print('astrbot\nollama')
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
            run("Start")
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
            run("Backup")
            assert len(list((root / "backups").glob("*.zip"))) == 1
            with zipfile.ZipFile(next((root / "backups").glob("*.zip"))) as backup:
                assert "data/astrbot/cmd_config.json" in backup.namelist()
                assert not any("docker-desktop" in name for name in backup.namelist())
            calls = [json.loads(line) for line in (root / "commands.jsonl").read_text().splitlines()]
            restarts = [args for args in calls if 'start' in args]
            assert restarts[-1][-3:] == ['start', 'astrbot', 'ollama']
            run('UpgradeCompanion')
            assert len(list((root / 'backups').glob('陪伴升级前-*.zip'))) == 1
            assert config.read_bytes() == saved
            (root / "fail-bootstrap").touch()
            run("Start", success=False)
            calls = [json.loads(line) for line in (root / "commands.jsonl").read_text().splitlines()]
            assert 'run' in calls[-1]  # Failed initialization never reaches up.
            run("Stop")
            assert config.read_bytes() == saved
            assert settings_path.read_text(encoding="utf-8") == json.dumps(settings)
        finally:
            for server in servers:
                server.shutdown()
                server.server_close()
    print("PASS: real PowerShell launcher + Chinese/spaced paths + disk guard + image lock + restart preservation + backup + failed bootstrap")


if __name__ == "__main__":
    main()
