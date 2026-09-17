#!/usr/bin/env python3
"""Fleet update reconciler (MAX-10 / P4). Runs on the host (not inside a
container — it manages Docker itself) as a systemd oneshot service, woken
periodically by vision-stand-updater.timer.

Pull-only by design: this device reaches out to GitHub and GHCR on its own
schedule and asks "what should I be running?" — nothing (CI included) ever
reaches inbound into the device. That's what makes an offline device a
non-issue: it just catches up whenever it next wakes, with no special case.

deploy/rollout.json in the repo is the single source of truth for what
version this device should run, keyed by device id. Deploy, canary and
rollback are all just edits to that file (see scripts/set_version.sh) —
this script's only job is reconciling local state to match it.
"""
import json
import logging
import subprocess
import sys
import time
import urllib.request

DEVICE_ID_FILE = '/etc/vision-stand/device-id'
ROLLOUT_URL = (
    'https://raw.githubusercontent.com/maxh1t/ros-dev-loop/main/deploy/rollout.json'
)
IMAGE_REPO = 'ghcr.io/maxh1t/ros-dev-loop'
VERSION_ENV_FILE = '/etc/vision-stand/version.env'
APP_SERVICE = 'vision-stand.service'
APP_CONTAINER = 'vision-stand'

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
log = logging.getLogger('updater')


def read_device_id():
    with open(DEVICE_ID_FILE) as f:
        return f.read().strip()


def fetch_rollout():
    with urllib.request.urlopen(ROLLOUT_URL, timeout=10) as resp:
        return json.load(resp)


def current_tag():
    result = subprocess.run(
        ['docker', 'inspect', '--format', '{{.Config.Image}}', APP_CONTAINER],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return None
    image = result.stdout.strip()
    return image.rsplit(':', 1)[-1] if ':' in image else None


CONTAINER_START_TIMEOUT_S = 15


def wait_for_container_running():
    """`systemctl restart` returns once the ExecStart process (the `docker
    run` CLI) has been forked, not once dockerd has actually created and
    started the named container — a `docker exec` right after restart can
    race that and see "No such container". Poll briefly rather than assume.
    """
    deadline = time.monotonic() + CONTAINER_START_TIMEOUT_S
    while time.monotonic() < deadline:
        result = subprocess.run(
            ['docker', 'inspect', '--format', '{{.State.Running}}', APP_CONTAINER],
            capture_output=True, text=True,
        )
        if result.returncode == 0 and result.stdout.strip() == 'true':
            return True
        time.sleep(1)
    return False


def run_health_check():
    if not wait_for_container_running():
        log.error(f'{APP_CONTAINER} did not start within '
                   f'{CONTAINER_START_TIMEOUT_S}s')
        return False
    result = subprocess.run(
        ['docker', 'exec', APP_CONTAINER,
         '/entrypoint.sh', 'python3', '/workspace/healthcheck.py'],
        timeout=30,
    )
    return result.returncode == 0


def swap_to(tag):
    image = f'{IMAGE_REPO}:{tag}'
    log.info(f'Pulling {image}')
    subprocess.run(['docker', 'pull', image], check=True)

    with open(VERSION_ENV_FILE, 'w') as f:
        f.write(f'IMAGE_TAG={tag}\n')

    log.info(f'Restarting {APP_SERVICE} on {tag}')
    subprocess.run(['systemctl', 'restart', APP_SERVICE], check=True)

    healthy = run_health_check()
    log.info(f"Health check after swap to {tag}: {'PASS' if healthy else 'FAIL'}")
    return healthy


def main():
    device_id = read_device_id()
    rollout = fetch_rollout()

    if device_id not in rollout:
        log.error(f'Device id {device_id!r} not in rollout.json — nothing to do')
        return

    desired = rollout[device_id]
    if not desired:
        log.info('No tag assigned yet — nothing to do')
        return

    running = current_tag()
    if running == desired:
        log.info(f'Already on {desired}, nothing to do')
        return

    log.info(f'Desired={desired} running={running!r} — updating')
    swap_to(desired)


if __name__ == '__main__':
    main()
