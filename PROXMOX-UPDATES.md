# Enable Declan release updates on CT 108

This assumes Declan runs as the `declan` service user from `/opt/declan-2`. Run setup as root after installing this build. The current Git checkout and `.data` stay in place. Updates now require administrator-approved commit hashes and a stable launcher outside downloaded releases.

```bash
cd /opt/declan-2
if release=$(git describe --tags --exact-match HEAD 2>/dev/null); then
  printf '%s\n' "$release" > .declan-release
fi
install -d -o declan -g declan -m 0750 /opt/declan-deploy /opt/declan-deploy/releases
ln -s /opt/declan-2 /opt/declan-deploy/current
install -d -o root -g root -m 0755 /usr/local/lib/declan /etc/declan
install -o root -g root -m 0644 update_supervisor.py /usr/local/lib/declan/update_supervisor.py
printf '{}\n' > /etc/declan/trusted-releases.json
chown root:root /etc/declan/trusted-releases.json
chmod 0644 /etc/declan/trusted-releases.json
systemctl edit declan
```

Add the following override:

```ini
[Service]
Environment=DECLAN_UPDATE_ROOT=/opt/declan-deploy
WorkingDirectory=/opt/declan-deploy/current
ExecStart=
ExecStart=/usr/bin/python3 /usr/local/lib/declan/update_supervisor.py --root /opt/declan-deploy
KillMode=mixed
Restart=on-failure
RestartSec=3
```

Restart the service and check its local health endpoint:

```bash
systemctl restart declan
/opt/declan-2/.venv/bin/python -c 'from urllib.request import urlopen; print(urlopen("http://127.0.0.1:52737/health").read().decode())'
```

Before offering a release, an administrator must independently review its exact commit and add a `"version-tag": "40-character-lowercase-commit-sha"` entry to `/etc/declan/trusted-releases.json`. Use the peeled commit SHA for annotated tags. The file and all parent directories must be root-owned, have no group/other write permission and contain no symlinks. Keep trust approval separate from the GitHub tag listing. An empty allow-list offers no updates. Do not make this file writable by `declan`, or generate approvals automatically from `ls-remote`.

Open Declan Web through the localhost SSH tunnel and select **Updates** beside the release badge. Only approved version tags are offered. The staged checkout must match the approved commit before running pip or any release code. Dependencies install as wheels with `--require-hashes`; releases with unhashed requirements fail safely. Each build gets its own Python environment, while all builds share the existing `.data`. The service keeps using `/etc/declan/declan.env`.

The stable launcher starts each selected release and allows 30 seconds for a local `/health` response belonging to the child process. If the executable is missing, the child exits, or health fails, it stops that child, atomically selects `previous`, and launches it. If rollback also fails, it exits for systemd to report/retry. It forwards service shutdown to the child. Install launcher changes separately as root; updates cannot replace the stable copy.

After a healthy start, cleanup retains the three newest release directories and three newest upgrade snapshots, plus any older current/previous releases. Virtual environments are removed with their releases. Symlink entries are never traversed for deletion. This bounds historical copies of deleted voice samples to the retained snapshots; deleting a sample does not erase those snapshots immediately.

Rollback restores application code, not shared data. Release migrations must remain backward compatible with `previous`; take a container backup before a schema-breaking upgrade. The startup check verifies the local server, not real Home Assistant playback or every endpoint.

Before testing a downgrade that may change stored data, take a container backup. If the selected build fails to start or predates the Updates button, restore the last build from the container console:

```bash
previous=$(readlink -f /opt/declan-deploy/previous) &&
  test -f "$previous/server.py" &&
  ln -sfn "$previous" /opt/declan-deploy/current &&
  systemctl restart declan
```
