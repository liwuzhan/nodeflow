#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Install NodeFlow edge services for a farm LAN deployment.

Usage:
  sudo scripts/install_edge_service.sh \
    --root /opt/nodeflow \
    --machine-id tractor-01 \
    --cloud-ip 192.168.10.10 \
    --config /opt/nodeflow/examples/tillage_operation.yaml

Options:
  --root PATH          NodeFlow repository path on this edge machine.
  --machine-id ID      Stable machine id shown in cloud dashboard.
  --cloud-ip IP        Cloud Box LAN IP.
  --config PATH        Runtime YAML used by nodeflow-runtime.service.
  --mqtt-port PORT     MQTT broker port. Default: 1883.
  --api-port PORT      Cloud API port. Default: 8080.
  --user USER          Service user. Default: current sudo user, or root.
  --python PATH        Python executable. Default: python3.
  --no-enable          Write files but do not enable/start services.
  -h, --help           Show this help.
EOF
}

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    echo "ERROR: run with sudo/root so systemd units can be installed." >&2
    exit 1
  fi
}

systemd_available() {
  command -v systemctl >/dev/null 2>&1 && [[ -d /etc/systemd/system ]]
}

quote_env() {
  local value="$1"
  printf "'%s'" "${value//\'/\'\\\'\'}"
}

ROOT=""
MACHINE_ID=""
CLOUD_IP=""
CONFIG=""
MQTT_PORT="1883"
API_PORT="8080"
SERVICE_USER="${SUDO_USER:-root}"
PYTHON_BIN="python3"
ENABLE_SERVICES=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --root)
      ROOT="$2"
      shift 2
      ;;
    --machine-id)
      MACHINE_ID="$2"
      shift 2
      ;;
    --cloud-ip)
      CLOUD_IP="$2"
      shift 2
      ;;
    --config)
      CONFIG="$2"
      shift 2
      ;;
    --mqtt-port)
      MQTT_PORT="$2"
      shift 2
      ;;
    --api-port)
      API_PORT="$2"
      shift 2
      ;;
    --user)
      SERVICE_USER="$2"
      shift 2
      ;;
    --python)
      PYTHON_BIN="$2"
      shift 2
      ;;
    --no-enable)
      ENABLE_SERVICES=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

require_root

if ! systemd_available; then
  echo "ERROR: systemd is required for this installer." >&2
  exit 1
fi

if [[ -z "${ROOT}" || -z "${MACHINE_ID}" || -z "${CLOUD_IP}" || -z "${CONFIG}" ]]; then
  echo "ERROR: --root, --machine-id, --cloud-ip, and --config are required." >&2
  usage >&2
  exit 1
fi

if [[ ! -d "${ROOT}" ]]; then
  echo "ERROR: NodeFlow root does not exist: ${ROOT}" >&2
  exit 1
fi

if [[ ! -f "${CONFIG}" ]]; then
  echo "ERROR: runtime config does not exist: ${CONFIG}" >&2
  exit 1
fi

install -d -m 0755 /etc/nodeflow

cat > /etc/nodeflow/edge.env <<EOF
NODEFLOW_ROOT=$(quote_env "${ROOT}")
NODEFLOW_CONFIG=$(quote_env "${CONFIG}")
NF_MACHINE_ID=$(quote_env "${MACHINE_ID}")
NF_MQTT_BROKER=$(quote_env "${CLOUD_IP}")
NF_MQTT_PORT=$(quote_env "${MQTT_PORT}")
NF_HTTP_SERVER_URL=$(quote_env "http://${CLOUD_IP}:${API_PORT}")
NF_TASK_AUTO_ACCEPT='true'
PYTHONPATH=$(quote_env "${ROOT}")
EOF

cat > /etc/systemd/system/nodeflow-runtime.service <<EOF
[Unit]
Description=NodeFlow Runtime Daemon
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
EnvironmentFile=/etc/nodeflow/edge.env
WorkingDirectory=${ROOT}
ExecStart=${PYTHON_BIN} -m runtime.main \${NODEFLOW_CONFIG} --daemon
Restart=always
RestartSec=3
KillSignal=SIGTERM

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/nodeflow-agent.service <<EOF
[Unit]
Description=NodeFlow MQTT TaskAgent
After=network-online.target nodeflow-runtime.service
Wants=network-online.target
Requires=nodeflow-runtime.service

[Service]
Type=simple
User=${SERVICE_USER}
EnvironmentFile=/etc/nodeflow/edge.env
WorkingDirectory=${ROOT}
ExecStart=${PYTHON_BIN} -m runtime.task.agent_main
Restart=always
RestartSec=3
KillSignal=SIGTERM

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload

if [[ "${ENABLE_SERVICES}" -eq 1 ]]; then
  systemctl enable nodeflow-runtime.service nodeflow-agent.service
  systemctl restart nodeflow-runtime.service
  systemctl restart nodeflow-agent.service
fi

cat <<EOF
Installed NodeFlow edge services.

Environment:
  /etc/nodeflow/edge.env

Services:
  nodeflow-runtime.service
  nodeflow-agent.service

Check:
  systemctl status nodeflow-runtime.service
  systemctl status nodeflow-agent.service
  journalctl -u nodeflow-agent.service -f
EOF
