# Enable Declan release updates on CT 108

This assumes Declan runs as the `declan` service user from `/opt/declan-2`. Run setup as root after installing this build. The current Git checkout and `.data` stay in place. Updates use published stable releases from the fixed NeoWeb-JP/Declan-2.0 repository and a stable launcher outside downloaded releases. Publishing a release is the approval step; there is no separate server edit for each version.

```bash
cd /opt/declan-2
if release=$(git describe --tags --exact-match HEAD 2>/dev/null); then
  printf '%s\n' "$release" > .declan-release
fi
install -d -o declan -g declan -m 0750 /opt/declan-deploy /opt/declan-deploy/releases
ln -s /opt/declan-2 /opt/declan-deploy/current
install -d -o root -g root -m 0755 /usr/local/lib/declan /etc/declan
install -o root -g root -m 0644 update_supervisor.py /usr/local/lib/declan/update_supervisor.py
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

## Normal release updates

The default `DECLAN_UPDATE_SOURCE=github` needs no additional configuration. Publish a non-draft, non-prerelease version in GitHub Releases, then click **Check for updates** and **Install selected release**. Plain Git tags and prerelease version suffixes are not offered in this channel. Up to the latest 100 GitHub release records are considered, sorted by numeric version for the menu. GitHub API or Git failures show an error and invalidate the previous choices; there is no silent fallback to the old allow-list.

Publishing access to `NeoWeb-JP/Declan-2.0` is now the trust boundary. Discovery uses HTTPS against GitHub's fixed releases API and Git remote; no download locations from release metadata are followed. This is repository trust, not independent release signing. Protect repository/release publishing access accordingly. Existing `trusted-releases.json` contents are retained but are not consulted by the default channel.

Each update check records the exact tag object and peeled commit. Installation rechecks that the release is still published and stable and that its identities still match. The cloned tag, HEAD and peeled commit must also match before Python environments, dependencies or release code run. A tag moved during discovery or cloning is rejected. Release withdrawal after the final publication check cannot be observed atomically, but a changed commit cannot pass the cloned-identity check.

Staging still installs wheels with `--require-hashes`, takes a private state snapshot before activation and retains the stable launcher's startup health check and rollback. All builds share the existing `.data`, and the service keeps using `/etc/declan/declan.env`. Updates are installed only when requested in the panel.

## Upgrading an installation with the old updater

Builds through 0.10.0 still require per-release pins. Getting this updater change onto such an installation requires one final approved upgrade through that old mechanism, or an administrator's normal manual deployment of the reviewed build. Once running this change, future published stable releases appear automatically. No new signing key, cron task or editable approval file is required for the default channel.

## Optional manual pinning

For installations that deliberately require independent per-release approval, set `DECLAN_UPDATE_SOURCE=pinned` in `/etc/declan/declan.env` and restart the service. This explicit mode retains `DECLAN_TRUSTED_RELEASES` (default `/etc/declan/trusted-releases.json`). Add a `"version-tag": "40-character-lowercase-commit-sha"` entry only after independent review; use the peeled commit for annotated tags. Only matching tag/commit pairs are offered, even without a GitHub Release record.

The file and all parent directories must be root-owned, have no group/other write permission and contain no symlinks. Do not make it writable by `declan`. An empty allow-list offers no updates in pinned mode. Do not automatically populate manual approvals from `ls-remote`. An invalid update-source setting fails rather than switching modes.

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
