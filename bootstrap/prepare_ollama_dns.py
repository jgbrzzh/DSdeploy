"""Repair Fake-IP resolution only for the verified official model CDN.

Keep Ollama's redirect protection enabled. Ask AliDNS over HTTPS for a public
address, and return a container-scoped hosts mapping. Never print signed URLs.
"""
import ipaddress
import json
import socket
import urllib.error
import urllib.parse
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def resolve_if_fake(host, overrides):
    addresses = [ipaddress.ip_address(item[4][0]) for item in socket.getaddrinfo(host, 443)]
    if addresses and all(address.is_global for address in addresses):
        return
    query = urllib.parse.urlencode({'name': host, 'type': 'A'})
    with urllib.request.urlopen('https://dns.alidns.com/resolve?' + query, timeout=20) as response:
        resolved = json.load(response)
    public = [record['data'] for record in resolved.get('Answer', [])
              if record.get('type') == 1 and ipaddress.ip_address(record['data']).is_global]
    if not public:
        raise ValueError('No verified public IPv4 address returned for official model host')
    overrides[host] = public[0]


def prepare():
    root = 'https://registry.ollama.ai/v2/library/bge-m3'
    overrides = {}
    resolve_if_fake('registry.ollama.ai', overrides)
    with urllib.request.urlopen(root + '/manifests/latest', timeout=20) as response:
        manifest = json.load(response)
    opener = urllib.request.build_opener(NoRedirect)
    for layer in manifest.get('layers', []):
        if layer.get('mediaType') != 'application/vnd.ollama.image.model':
            continue
        digest = str(layer.get('digest', ''))
        if not digest.startswith('sha256:') or len(digest) != 71:
            raise ValueError('Invalid official model digest')
        try:
            with opener.open(urllib.request.Request(root + '/blobs/' + digest,
                                                   headers={'Range': 'bytes=0-0'}), timeout=20):
                continue
        except urllib.error.HTTPError as error:
            if error.code not in (301, 302, 303, 307, 308):
                raise
            target = urllib.parse.urlsplit(error.headers.get('Location', ''))
        host = target.hostname or ''
        if target.scheme != 'https' or target.username or target.port not in (None, 443):
            raise ValueError('Unexpected model redirect')
        if not host.endswith('.r2.cloudflarestorage.com'):
            continue  # Do not override unrecognized CDN domains.
        resolve_if_fake(host, overrides)
    return {'services': {'ollama': {'extra_hosts': overrides}}} if overrides else {}


if __name__ == '__main__':
    try:
        print(json.dumps(prepare()))
    except Exception:
        # Network repair is optional; the ordinary official pull still runs.
        print('{}')
