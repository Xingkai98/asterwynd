#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "This helper must run as root." >&2
  exit 1
fi

if docker info >/dev/null 2>&1; then
  echo "Docker daemon is already available."
  exit 0
fi

mkdir -p /run/containerd

if ! pgrep -x containerd >/dev/null 2>&1; then
  echo "Starting containerd..."
  nohup containerd >/tmp/asterwynd-containerd.log 2>&1 &
fi

for _ in $(seq 1 20); do
  if [ -S /run/containerd/containerd.sock ]; then
    break
  fi
  sleep 1
done

if [ ! -S /run/containerd/containerd.sock ]; then
  echo "containerd socket not ready: /run/containerd/containerd.sock" >&2
  exit 1
fi

echo "Starting dockerd..."
docker_args=(
  --containerd=/run/containerd/containerd.sock
  --iptables=false
  --bridge=none
  --ip-forward=false
  --ip-masq=false
)

if ! grep -q '"storage-driver"' /etc/docker/daemon.json 2>/dev/null; then
  docker_args+=(--storage-driver=vfs)
fi

exec dockerd "${docker_args[@]}"
