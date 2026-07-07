#!/usr/bin/env bash
#
# deploy.sh — DRAFT template for deploying ros-dev-loop to a Raspberry Pi.
#
# STATUS: NOT RUNNABLE YET. The Pi is not configured; host/user/path below are
# placeholders. In Part 6, fill in the real values and uncomment the steps.
#
# What it will do once completed:
#   1. rsync the src/ tree to the Pi
#   2. ssh into the Pi and run `colcon build`
#   3. restart the detector node on the Pi
#
# ---------------------------------------------------------------------------
# set -euo pipefail
#
# # --- Pi connection settings (placeholders — replace in Part 6) ----------
# PI_HOST="raspberrypi.local"          # e.g. 192.168.1.42
# PI_USER="pi"                         # SSH user on the Pi
# PI_PATH="/home/pi/ros-dev-loop"      # workspace path on the Pi
#
# # Local workspace root (directory containing this script's parent)
# WORKSPACE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
#
# # --- Step 1: sync source to the Pi --------------------------------------
# # Only src/ is copied; build/ install/ log/ are rebuilt on the Pi.
# rsync -az --delete \
#   "${WORKSPACE_ROOT}/src/" \
#   "${PI_USER}@${PI_HOST}:${PI_PATH}/src/"
#
# # --- Step 2: build on the Pi --------------------------------------------
# ssh "${PI_USER}@${PI_HOST}" bash -lc "\
#   source /opt/ros/jazzy/setup.bash && \
#   cd ${PI_PATH} && \
#   colcon build"
#
# # --- Step 3: restart the detector node ----------------------------------
# # Placeholder: adapt to however the node runs on the Pi (systemd unit,
# # tmux session, plain ros2 run, ...).
# ssh "${PI_USER}@${PI_HOST}" bash -lc "\
#   source /opt/ros/jazzy/setup.bash && \
#   source ${PI_PATH}/install/setup.bash && \
#   sudo systemctl restart detector.service"
# ---------------------------------------------------------------------------

echo "deploy.sh is a draft template and does nothing yet."
echo "Fill in the Pi settings and uncomment the steps before using it."
exit 1
