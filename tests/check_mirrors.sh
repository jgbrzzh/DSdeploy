#!/bin/sh
for host in docker.m.daocloud.io docker.1ms.run; do
    for repo in soulter/astrbot mlikiowa/napcat-docker ollama/ollama; do
        printf '%s/%s ' "$host" "$repo"
        curl --max-time 12 -sS -o /tmp/mirror-check -w '%{http_code}\n' \
            -H 'Accept: application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json' \
            "https://$host/v2/$repo/manifests/latest"
        head -c 140 /tmp/mirror-check
        printf '\n'
    done
done
