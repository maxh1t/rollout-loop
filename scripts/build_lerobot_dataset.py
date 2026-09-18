#!/usr/bin/env python3
"""Folds Pi-captured snapshots (from take_snapshot) into a local
LeRobotDataset.

Dev-machine-only, like scripts/export_model.py: `lerobot` pulls in
torch/torchvision/av, so it lives in its own throwaway venv, never on the Pi.

Usage (from repo root):
    python3 -m venv .venv-lerobot
    source .venv-lerobot/bin/activate
    pip install 'lerobot[dataset]'
    python3 scripts/build_lerobot_dataset.py

A detection snapshot has no robot action/state, so there's nowhere in
LeRobotDataset's schema for the detection result to live — this script
folds a human-readable summary into the per-frame `task` field instead, and
separately copies the full sidecar JSON into `<root>/source_metadata/`.
"""
import argparse
import json
import shutil
import subprocess
from pathlib import Path

import cv2

from lerobot.datasets.lerobot_dataset import LeRobotDataset
from lerobot.utils.feature_utils import hw_to_dataset_features

INGESTED_MARKER = '.ros_dev_loop_ingested.json'


def rsync_from_pi(pi_host, remote_snapshot_dir, local_staging_dir):
    local_staging_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ['rsync', '-av', f'{pi_host}:{remote_snapshot_dir}/', f'{local_staging_dir}/'],
        check=True)


def load_ingested(root):
    marker = root / INGESTED_MARKER
    if marker.exists():
        return set(json.loads(marker.read_text()))
    return set()


def save_ingested(root, ingested):
    (root / INGESTED_MARKER).write_text(json.dumps(sorted(ingested), indent=2))


def summarize_task(detections):
    if not detections:
        return 'no detections'
    return '; '.join(f'{d["class_name"]} {d["score"]:.2f}' for d in detections)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pi-host', default='pi')
    parser.add_argument('--remote-snapshot-dir', default='~/vision_stand_snapshots')
    parser.add_argument('--local-staging-dir',
                         default=str(Path.home() / 'vision_stand_snapshots_staging'))
    parser.add_argument('--repo-id', default='vision_stand/snapshots')
    parser.add_argument('--root', default=str(Path.home() / 'lerobot_datasets' / 'vision_stand'))
    parser.add_argument('--skip-rsync', action='store_true',
                         help='use whatever is already in --local-staging-dir')
    args = parser.parse_args()

    staging_dir = Path(args.local_staging_dir)
    root = Path(args.root)

    if not args.skip_rsync:
        rsync_from_pi(args.pi_host, args.remote_snapshot_dir, staging_dir)

    ingested = load_ingested(root) if root.exists() else set()
    pending = sorted(
        p for p in staging_dir.glob('snapshot_*.json') if p.name not in ingested)

    if not pending:
        print('Nothing new to ingest.')
        return

    dataset_already_exists = (root / 'meta' / 'info.json').exists()

    dataset = None
    for json_path in pending:
        meta = json.loads(json_path.read_text())
        jpg_path = json_path.with_suffix('.jpg')
        img_bgr = cv2.imread(str(jpg_path))
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        h, w, c = img_rgb.shape

        if dataset is None:
            if dataset_already_exists:
                dataset = LeRobotDataset.resume(repo_id=args.repo_id, root=root)
            else:
                features = hw_to_dataset_features(
                    {'cam': (h, w, c)}, prefix='observation', use_video=False)
                dataset = LeRobotDataset.create(
                    repo_id=args.repo_id, fps=1, features=features, root=root,
                    use_videos=False)
            (root / 'source_metadata').mkdir(parents=True, exist_ok=True)

        dataset.add_frame({
            'observation.images.cam': img_rgb,
            'task': summarize_task(meta['detections']),
        })
        dataset.save_episode()

        shutil.copy(json_path, root / 'source_metadata' / json_path.name)
        ingested.add(json_path.name)
        print(f'Ingested {json_path.name}')

    dataset.finalize()
    save_ingested(root, ingested)
    print(f'Dataset at {root}: {dataset.num_episodes} episodes, {dataset.num_frames} frames.')


if __name__ == '__main__':
    main()
