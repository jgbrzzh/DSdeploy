"""Probe real registry manifests with anonymous Bearer authentication."""
import concurrent.futures
import json
import re
import urllib.error
import urllib.parse
import urllib.request

ACCEPT = 'application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json'


def probe(item):
    host, repo = item
    url = f'https://{host}/v2/{repo}/manifests/latest'
    headers = {'Accept': ACCEPT}
    result = {'image': f'{host}/{repo}:latest'}
    try:
        try:
            response = urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=15)
        except urllib.error.HTTPError as error:
            if error.code != 401:
                raise
            challenge = dict(re.findall(r'(\w+)="([^"]*)"', error.headers.get('WWW-Authenticate', '')))
            token_url = challenge['realm'] + '?' + urllib.parse.urlencode({k: v for k, v in challenge.items() if k != 'realm'})
            token_data = json.load(urllib.request.urlopen(token_url, timeout=15))
            headers['Authorization'] = 'Bearer ' + (token_data.get('token') or token_data['access_token'])
            response = urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20)
        result.update(status=response.status, digest=response.headers.get('Docker-Content-Digest'))
        body = json.load(response)
        result['media_type'] = body.get('mediaType')
        result['platforms'] = [m.get('platform') for m in body.get('manifests', [])]
    except Exception as error:
        result['error'] = str(error)
    return result


if __name__ == '__main__':
    cases = [(host, repo) for host in ['docker.m.daocloud.io', 'docker.1ms.run']
             for repo in ['soulter/astrbot', 'mlikiowa/napcat-docker', 'ollama/ollama']]
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        for result in pool.map(probe, cases):
            print(json.dumps(result), flush=True)
