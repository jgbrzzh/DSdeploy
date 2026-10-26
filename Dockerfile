ARG ASTRBOT_BASE=soulter/astrbot:latest
FROM ${ASTRBOT_BASE}
COPY vendor /opt/dsdeploy-vendor
COPY bootstrap/install_plugins.py /opt/dsdeploy-install.py
RUN python /opt/dsdeploy-install.py /opt/dsdeploy-vendor /opt/dsdeploy-plugins /tmp/dsdeploy-core-constraints.txt \
    && python -m pip install --no-cache-dir -c /tmp/dsdeploy-core-constraints.txt \
       -r /opt/dsdeploy-plugins/astrbot_plugin_livingmemory/requirements.txt \
       -r /opt/dsdeploy-plugins/astrbot_plugin_proactive_chat/requirements.txt \
    && python -m pip check
WORKDIR /AstrBot
