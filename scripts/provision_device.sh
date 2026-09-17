#!/usr/bin/env bash
# One-time setup for a new fleet device (MAX-10 / P4) — run from the
# operator's machine over SSH. The device itself never needs a checkout of
# this repo, ROS, or a build toolchain — just Docker, plus the handful of
# small files this script copies over.
#
# Usage: scripts/provision_device.sh <ssh-host> <device-id> <app-unit>
#   <ssh-host>   SSH alias/host for the device (e.g. pi)
#   <device-id>  key this device will use in deploy/rollout.json (e.g. pi5)
#   <app-unit>   vision-stand.service (real camera) or vision-stand-sim.service (file source)
set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "Usage: $0 <ssh-host> <device-id> <vision-stand.service|vision-stand-sim.service>" >&2
  exit 1
fi

host="$1"
device_id="$2"
app_unit="$3"
repo_root="$(cd "$(dirname "$0")/.." && pwd)"

ssh "$host" "sudo mkdir -p /etc/vision-stand /opt/vision-stand"

scp "$repo_root/deploy/updater.py" "$host:/tmp/updater.py"
scp "$repo_root/deploy/systemd/$app_unit" "$host:/tmp/vision-stand.service"
scp "$repo_root/deploy/systemd/vision-stand-foxglove.service" "$host:/tmp/"
scp "$repo_root/deploy/systemd/vision-stand-updater.service" "$host:/tmp/"
scp "$repo_root/deploy/systemd/vision-stand-updater.timer" "$host:/tmp/"
if [[ "$app_unit" == "vision-stand-sim.service" ]]; then
  scp "$repo_root/test_clip.mp4" "$host:/tmp/test_clip.mp4"
fi

ssh "$host" bash -s "$device_id" "$app_unit" <<'REMOTE'
set -euo pipefail
device_id="$1"
app_unit="$2"

if ! command -v docker >/dev/null; then
  echo "Installing Docker..."
  sudo apt-get update
  sudo apt-get install -y docker.io
  sudo systemctl enable --now docker
fi

echo "$device_id" | sudo tee /etc/vision-stand/device-id >/dev/null
[[ -f /etc/vision-stand/version.env ]] || echo "IMAGE_TAG=" | sudo tee /etc/vision-stand/version.env >/dev/null

if [[ "$app_unit" == "vision-stand.service" ]]; then
  # A stable by-id path, not a raw /dev/videoN index -- USB re-enumeration
  # after an unplug/replug can move which index a camera lands on.
  camera_source=$(ls /dev/v4l/by-id/*-video-index0 2>/dev/null | head -1 || true)
  if [[ -z "$camera_source" ]]; then
    echo "WARNING: no /dev/v4l/by-id/*-video-index0 found, falling back to /dev/video0 (not hotplug-safe)" >&2
    camera_source="/dev/video0"
  fi
  sudo sed -i '/^CAMERA_SOURCE=/d' /etc/vision-stand/version.env
  echo "CAMERA_SOURCE=$camera_source" | sudo tee -a /etc/vision-stand/version.env >/dev/null
  echo "Detected camera: $camera_source"
fi

sudo mv /tmp/updater.py /opt/vision-stand/updater.py
sudo chmod +x /opt/vision-stand/updater.py

if [[ "$app_unit" == "vision-stand-sim.service" ]]; then
  sudo mv /tmp/test_clip.mp4 /opt/vision-stand/test_clip.mp4
fi

sudo mv /tmp/vision-stand.service /etc/systemd/system/vision-stand.service
sudo mv /tmp/vision-stand-foxglove.service /etc/systemd/system/
sudo mv /tmp/vision-stand-updater.service /etc/systemd/system/
sudo mv /tmp/vision-stand-updater.timer /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable --now vision-stand.service
sudo systemctl enable --now vision-stand-foxglove.service
sudo systemctl enable --now vision-stand-updater.timer

echo "Provisioned as device-id=$device_id."
REMOTE

echo "Next: set deploy/rollout.json[\"$device_id\"], commit, push,"
echo "then: ssh $host sudo systemctl start vision-stand-updater.service"
