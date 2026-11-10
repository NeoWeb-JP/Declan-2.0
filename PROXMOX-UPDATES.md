# Enable Declan release updates on CT 108

This assumes Declan runs as the `declan` service user from `/opt/declan-2` and has `Restart=on-failure` in its systemd unit. Run setup as root after installing a build that contains `updates.py`. The current Git checkout and `.data` stay in place.

```bash
cd /opt/declan-2
if release=$(git describe --tags --exact-match HEAD 2>/dev/null); then
  printf '%s\n' "$release" > .declan-release
fi
install -d -o declan -g declan -m 0750 /opt/declan-deploy /opt/declan-deploy/releases
ln -s /opt/declan-2 /opt/declan-deploy/current
systemctl edit declan
```

Add the following override:

```ini
[Service]
Environment=DECLAN_UPDATE_ROOT=/opt/declan-deploy
WorkingDirectory=/opt/declan-deploy/current
ExecStart=
ExecStart=/opt/declan-deploy/current/.venv/bin/python /opt/declan-deploy/current/server.py --assist-lan
Restart=on-failure
RestartSec=3
```

Restart the service and check its local health endpoint:

```bash
systemctl restart declan
/opt/declan-2/.venv/bin/python -c 'from urllib.request import urlopen; print(urlopen("http://127.0.0.1:52737/health").read().decode())'
```

Open Declan Web through the localhost SSH tunnel and select **Updates** beside the release badge. Select a versioned Git tag and choose **Install selected release**. Older tags are available for rollback. Each build gets its own Python environment, while all builds share the existing `.data`. The service keeps using `/etc/declan/declan.env`.

Before testing a downgrade that may change stored data, take a container backup. If the selected build fails to start or predates the Updates button, restore the last build from the container console:

```bash
previous=$(readlink -f /opt/declan-deploy/previous) &&
  test -f "$previous/server.py" &&
  ln -sfn "$previous" /opt/declan-deploy/current &&
  systemctl restart declan
```
