"""Real Windows PowerShell migration, simulated Docker and synthetic user data.

No personal data, QQ session, model request, or real Docker project is used.
"""
import hashlib
from contextlib import closing
import http.server
import json
import os
import shutil
import socketserver
import sqlite3
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSIONS = ('1.0.0', '1.1.0', '1.2.0', '1.2.1', '1.3.0', '1.3.1')

MOCK = r'''
import json, os, sys
from pathlib import Path
root=Path(os.environ['DSDEPLOY_MIGRATION_FIXTURE'])
args=sys.argv[1:]
state=json.loads((root/'docker-state.json').read_text(encoding='utf-8'))
with (root/'calls.jsonl').open('a',encoding='utf-8') as out: out.write(json.dumps(args)+'\n')
def save(): (root/'docker-state.json').write_text(json.dumps(state),encoding='utf-8')
def item(cid):
 c=state['containers'][cid]
 return dict(Id=cid, Image=c['image'], State=dict(Running=c['running']),
  Config=dict(Labels={'com.docker.compose.project.working_dir':c['root'],
                      'com.docker.compose.service':c['service']}),
  HostConfig=dict(RestartPolicy=dict(Name=c['restart'],MaximumRetryCount=c.get('retries',0)),PortBindings=c.get('ports',{})),
  Mounts=c.get('mounts',[]))
if args[0]=='info': print('linux'); sys.exit(0)
if args[:2]==['compose','version']: print('2.40.0'); sys.exit(0)
if args[:2]==['image','inspect']:
 name=args[2]
 if (root/'missing-image').exists(): sys.exit(1)
 image=state['images'].get(name)
 if not image: sys.exit(1)
 print(image if '--format' in args else json.dumps([dict(Id=image)])); sys.exit(0)
if args[0]=='inspect': print(json.dumps([item(args[1])]))
elif args[0]=='ps':
 project=args[-1].rsplit('=',1)[-1]
 print('\n'.join(cid for cid,c in state['containers'].items() if c['project']==project))
elif args[0]=='stop':
 if args[-1].startswith('new-') and (root/'fail-new-stop').exists(): sys.exit(43)
 state['containers'][args[-1]]['running']=False; save()
elif args[0]=='start': state['containers'][args[-1]]['running']=True; save()
elif args[0]=='update':
 policy=args[1].split('=',1)[1].split(':')
 state['containers'][args[-1]]['restart']=policy[0]
 state['containers'][args[-1]]['retries']=int(policy[1]) if len(policy)>1 else 0
 save()
elif args[0]=='tag': state['images'][args[2]]=state['images'][args[1]]; save()
elif args[0]=='compose':
 files=[Path(args[i+1]) for i,v in enumerate(args) if v=='-f']
 project=args[args.index('--project-name')+1]
 if 'config' in args:
  data=json.loads(files[0].read_text(encoding='utf-8-sig'))
  if '--format' in args: print(json.dumps(data))
 if 'up' in args:
  data=json.loads(files[0].read_text(encoding='utf-8-sig'))
  for service,cfg in data['services'].items():
   cid='new-'+service
   state['containers'][cid]=dict(root=str(files[0].parent),project=project,service=service,
     image=state['images'].get(cfg['image'],cfg['image']),running=True,restart='unless-stopped')
  save()
  if (root/'fail-up').exists(): sys.exit(42)
 if 'exec' in args: print('fixture ollama ready')
else: raise RuntimeError('unexpected command: '+repr(args))
'''


class Quiet(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'fixture panel')

    def log_message(self, *args):
        pass


def tree(path):
    return {p.relative_to(path).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in path.rglob('*') if p.is_file()}


def main():
    (ROOT / '.research').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='migration-中文 ', dir=ROOT / '.research') as folder:
        base = Path(folder)
        servers = [socketserver.TCPServer(('127.0.0.1', 0), Quiet) for _ in range(2)]
        ports = [s.server_address[1] for s in servers]
        for server in servers:
            threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            def scenario(version, failure=None):
                case = base / (version + '-' + (failure or 'success'))
                old, new = case / '旧版 包', case / '新版 $HOME 包'
                for path in [old, new]:
                    path.mkdir(parents=True)
                shutil.copy2(ROOT / 'Deploy.ps1', new)
                shutil.copy2(ROOT / 'Dockerfile', new)
                shutil.copy2(ROOT / 'compose.yaml', new)
                for directory in ['bootstrap', 'vendor']:
                    shutil.copytree(ROOT / directory, new / directory,
                                    ignore=shutil.ignore_patterns('__pycache__'))
                (new / 'private').mkdir()
                (new / 'private/original-target.txt').write_text('retain before migration')
                for relative in ['data/astrbot/config', 'data/astrbot/plugin_data/astrbot_plugin_livingmemory',
                                 'data/astrbot/plugins/custom_plugin', 'data/napcat', 'data/qq/nt_qq',
                                 'data/ollama/models/blobs', 'data/docker-desktop', 'private/docker-client']:
                    (old / relative).mkdir(parents=True)
                (old / 'VERSION').write_text(version)
                for relative, value in {
                    'data/astrbot/cmd_config.json': '{"personality":"custom","api_key":"fixture-only"}',
                    'data/astrbot/config/memory.json': '{"provider":"original","enabled":true}',
                    'data/astrbot/plugins/custom_plugin/main.py': '# user custom plugin: keep exact bytes\n',
                    'data/astrbot/plugin_data/astrbot_plugin_livingmemory/index.faiss': 'fixture-index-世界',
                    'data/astrbot/plugin_data/astrbot_plugin_livingmemory/recent.json': '{"session":"original"}',
                    'data/napcat/webui.json': '{"token":"old-token"}',
                    'data/napcat/onebot11.json': '{"url":"ws://astrbot:6199/ws","token":"same-token"}',
                    'data/qq/nt_qq/session.bin': 'fixture-qq-login',
                    'data/ollama/models/blobs/synthetic-model': 'fixture-model',
                    'data/docker-desktop/keep.vhdx': 'engine must never be copied',
                    'private/settings.json': '{"owner_qq":"12345678","custom":"unchanged"}',
                    'private/docker-client/config.json': '{}',
                    'private/面板登录信息.txt': 'original credentials and original addresses',
                }.items():
                    (old / relative).write_text(value, encoding='utf-8')
                for relative in ['data/astrbot/data_v4.db',
                                 'data/astrbot/plugin_data/astrbot_plugin_livingmemory/memory.db']:
                    with closing(sqlite3.connect(old / relative)) as db:
                        db.execute('CREATE TABLE memories (id INTEGER PRIMARY KEY, content TEXT)')
                        db.execute('INSERT INTO memories(content) VALUES (?)', ('旧记忆：主人喜欢茉莉花茶',))
                        db.commit()
                modern = tuple(map(int, version.split('.'))) >= (1, 3, 0)
                project = 'dsdeploy-0123456789' if modern else 'dsdeploy'
                image_name = 'dsdeploy-astrbot-0123456789:local' if modern else 'dsdeploy-astrbot:local'
                if modern:
                    (old / 'private/instance.json').write_text(json.dumps(dict(
                        root=str(old.resolve()).lower(), project=project, image=image_name,
                        astrbot_port=ports[0], napcat_port=ports[1])), encoding='utf-8')
                mounts = dict(astrbot=[('data/astrbot', '/AstrBot/data'), ('private','/deploy-private'), ('bootstrap','/bootstrap')],
                              napcat=[('data/napcat','/app/napcat/config'), ('data/qq','/app/.config/QQ'), ('data/astrbot','/AstrBot/data')],
                              ollama=[('data/ollama','/root/.ollama')])
                images = dict(astrbot=image_name, napcat='fixture/napcat:old', ollama='fixture/ollama:old')
                config = dict(name=project, services={}, networks={'default':{'name':project+'_default'}})
                state = dict(containers={}, images={})
                for index, service in enumerate(['astrbot','napcat','ollama']):
                    image_id = 'sha256:' + str(index+1)*64
                    state['images'][images[service]] = image_id
                    state['images'][image_id] = image_id
                    volumes=[dict(type='bind',source=str(old / rel),target=dest) for rel,dest in mounts[service]]
                    config['services'][service] = dict(image=images[service], volumes=volumes, restart='unless-stopped')
                    state['containers']['old-'+service] = dict(root=str(old), project=project,
                        service=service,image=image_id,running=service!='ollama',restart='on-failure',retries=3,
                        mounts=[dict(Type='bind',Source=str(old/rel),Destination=dest) for rel,dest in mounts[service] if rel.startswith('data/')])
                config['services']['astrbot']['build'] = dict(context=str(old),dockerfile='Dockerfile',args={})
                config['services']['astrbot']['environment']={'LITERAL':'synthetic$secret${value}'}
                config['services']['astrbot']['ports'] = [dict(target=6185,published=str(ports[0]),host_ip='127.0.0.1',protocol='tcp')]
                config['services']['napcat']['ports'] = [dict(target=6099,published=str(ports[1]),host_ip='127.0.0.1',protocol='tcp')]
                state['containers']['old-astrbot']['ports']={'6185/tcp':[{'HostPort':str(ports[0]),'HostIp':'127.0.0.1'}]}
                state['containers']['old-napcat']['ports']={'6099/tcp':[{'HostPort':str(ports[1]),'HostIp':'127.0.0.1'}]}
                config['services']['napcat']['dns'] = ['223.5.5.5','119.29.29.29']
                if failure == 'foreign':
                    state['containers']['old-astrbot']['root'] = str(case / 'another-user')
                if failure == 'external-bind':
                    config['services']['astrbot']['volumes'].append(dict(type='bind',source=str(case / 'external'),target='/external'))
                if failure == 'port-drift':
                    state['containers']['old-astrbot']['ports']['6185/tcp'][0]['HostPort']='12345'
                (old / 'compose.yaml').write_text(json.dumps(config), encoding='utf-8')
                (case / 'docker-state.json').write_text(json.dumps(state),encoding='utf-8')
                if failure in ('fail-up', 'missing-image'):
                    (case / failure).touch()
                if failure == 'interrupted':
                    (case / 'fail-up').touch()
                    (case / 'fail-new-stop').touch()
                if failure == 'junction':
                    subprocess.run(['cmd','/c','mklink','/J',str(old/'data/astrbot/link'),str(old/'data/qq')],
                                   capture_output=True,check=True)
                before = tree(old)
                target_before = tree(new / 'private')
                mock = case / 'bin'
                mock.mkdir()
                (mock / 'docker.py').write_text(MOCK,encoding='utf-8')
                (mock / 'docker.cmd').write_text('@echo off\n"'+sys.executable+'" "%~dp0docker.py" %*\n',encoding='utf-8')
                env={**os.environ,'PATH':str(mock)+os.pathsep+os.environ['PATH'], 'DSDEPLOY_MIGRATION_FIXTURE':str(case)}
                env.pop('PSModulePath',None)
                def run(action, success=True, source=old):
                    cmd=['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(new/'Deploy.ps1'),'-Action',action]
                    if action=='Migrate': cmd += ['-SourceDirectory',str(source)]
                    proc=subprocess.run(cmd,env=env,capture_output=True,timeout=90)
                    assert (proc.returncode==0)==success, (version,failure,proc.stdout.decode('utf-8',errors='replace'),proc.stderr.decode('utf-8',errors='replace'))
                run('Migrate', success=not failure)
                assert tree(old)==before, 'source files changed'
                if failure == 'interrupted':
                    assert json.loads((new/'migration.json').read_text(encoding='utf-8'))['status']=='switching'
                    run('Start',success=False)
                    (case/'fail-up').unlink()
                    (case/'fail-new-stop').unlink()
                    run('RollbackMigration')
                after=json.loads((case/'docker-state.json').read_text(encoding='utf-8'))
                if failure:
                    assert all(after['containers'][cid]['running']==c['running'] and after['containers'][cid]['restart']==c['restart']
                               for cid,c in state['containers'].items()), 'source state not restored'
                    assert (new/'private/original-target.txt').read_text()=='retain before migration'
                    if failure in ('foreign','external-bind','missing-image','port-drift'):
                        calls=[json.loads(line) for line in (case/'calls.jsonl').read_text(encoding='utf-8').splitlines()]
                        assert not any(c[0] in ('stop','update') for c in calls), 'preflight mutated source'
                    return
                receipt=json.loads((new/'migration.json').read_text(encoding='utf-8'))
                assert receipt['status']=='complete'
                assert all(not after['containers'][cid]['running'] and after['containers'][cid]['restart']=='no'
                           for cid in state['containers']), after
                for relative, digest in before.items():
                    if relative.startswith('data/docker-desktop/') or relative in ('compose.yaml','VERSION','private/instance.json'):
                        continue
                    assert hashlib.sha256((new/relative).read_bytes()).hexdigest()==digest, relative
                assert not (new/'data/docker-desktop').exists()
                migrated=json.loads((new/'compose.migrated.json').read_text(encoding='utf-8'))
                assert migrated['services']['astrbot']['ports']==config['services']['astrbot']['ports']
                assert migrated['services']['napcat']['dns']==config['services']['napcat']['dns']
                assert migrated['services']['napcat']['image']==state['images'][images['napcat']]
                assert migrated['services']['astrbot']['environment']['LITERAL']=='synthetic$$secret$${value}'
                assert all(str(old).lower() not in vol['source'].lower()
                           for service in migrated['services'].values() for vol in service['volumes'])
                assert all(vol['source'].replace('$$','$').lower().startswith(str(new).lower())
                           for service in migrated['services'].values() for vol in service['volumes'])
                identity=json.loads((new/'private/instance.json').read_text(encoding='utf-8'))
                assert identity['project']!=project and identity['astrbot_port']==ports[0] and identity['napcat_port']==ports[1]
                assert identity['docker_mode']=='shared'
                assert migrated['networks']['default']['name']==identity['project']+'_default'
                manifest=json.loads((Path(receipt['transaction'])/'files.json').read_text(encoding='utf-8'))
                assert any(entry['path'].endswith('index.faiss') for entry in manifest)
                for entry in manifest:
                    assert hashlib.sha256((Path(receipt['transaction'])/'source-snapshot'/entry['path']).read_bytes()).hexdigest()==entry['sha256'].lower()
                run('Migrate',success=False)
                # Rollback after new messages retains the new data rather than losing it.
                (new/'data/astrbot/new-message.txt').write_text('new memory after migration')
                run('RollbackMigration')
                run('RollbackMigration')  # repeat-safe
                rolled=json.loads((case/'docker-state.json').read_text(encoding='utf-8'))
                assert all(rolled['containers'][cid]['running']==c['running'] and rolled['containers'][cid]['restart']==c['restart']
                           and rolled['containers'][cid]['retries']==3 for cid,c in state['containers'].items())
                assert (Path(receipt['transaction'])/'new-version-retained/data/astrbot/new-message.txt').exists()
                # Initialize-Instance adds only its own identity/address files to the pre-migration target.
                assert all(tree(new/'private')[key]==value for key,value in target_before.items())
                assert tree(old)==before

            for version in VERSIONS:
                scenario(version)
            for failure in ('fail-up','foreign','external-bind','missing-image','junction','port-drift','interrupted'):
                scenario('1.0.0',failure)
            print('PASS: six historical layouts; byte-identical settings, SQLite memories, FAISS, plugin/session/model data; ports/images/DNS; rollback + retained new data; foreign/external/missing-image/link guards.')
        finally:
            for server in servers:
                server.shutdown()
                server.server_close()


if __name__=='__main__':
    main()
