#!/usr/bin/env bash
# Points one fleet device at a version, by editing deploy/rollout.json and
# pushing the change — then commits and pushes.
#
# This one script is both "promote" and "rollback" (MAX-10 / P4): promotion
# is pointing a device at a newer version, rollback is pointing it back at
# an older one that's already published. Same operation either way. Devices
# pick this up on their own via the updater's periodic check (see
# deploy/updater.py) — this script never touches a device directly.
#
# The normal case doesn't need this at all: bump <version> in
# src/detector/package.xml and this file's target in the same commit that
# changes the code, and CI publishes exactly that version. This script is
# for the exception -- rolling back, or moving vm-sim by hand for a canary
# test -- not the everyday push-and-forget loop.
#
# Usage: scripts/set_version.sh <device-id> <version>
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "Usage: $0 <device-id> <version>" >&2
  exit 1
fi

device_id="$1"
tag="$2"
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
rollout_file="$repo_root/deploy/rollout.json"

python3 - "$rollout_file" "$device_id" "$tag" <<'EOF'
import json
import sys

path, device_id, tag = sys.argv[1:4]
with open(path) as f:
    data = json.load(f)

if device_id not in data:
    print(f"Unknown device id {device_id!r}. Known devices: {list(data)}", file=sys.stderr)
    sys.exit(1)

data[device_id] = tag
with open(path, "w") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
EOF

git -C "$repo_root" add "$rollout_file"
git -C "$repo_root" commit -m "Set ${device_id} -> ${tag}"
git -C "$repo_root" push
