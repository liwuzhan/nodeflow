#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Install NodeFlow cloud services for a farm LAN Cloud Box.

Usage:
  sudo scripts/install_cloud_lan.sh \
    --root /opt/nodeflow \
    --host 0.0.0.0 \
    --port 8080 \
    --web-port 5173 \
    --public-base-url http://192.168.10.10:8080

Options:
  --root PATH             NodeFlow repository path on the Cloud Box.
  --host HOST             FastAPI bind host. Default: 0.0.0.0.
  --port PORT             FastAPI port. Default: 8080.
  --web-host HOST         Web bind host. Default: 0.0.0.0.
  --web-port PORT         Web port. Default: 5173.
  --mqtt-broker HOST      MQTT broker host used by cloud API. Default: 127.0.0.1.
  --mqtt-port PORT        MQTT broker port. Default: 1883.
  --public-base-url URL   API URL reachable by edge machines. Required.
  --database-url URL      SQLAlchemy database URL. Default: sqlite:////<root>/cloud/server/farm.db.
  --user USER             Service user. Default: current sudo user, or root.
  --python PATH           Python executable. Default: python3.
  --npm PATH              npm executable. Default: npm.
  --no-mosquitto          Do not enable/start mosquitto.service.
  --no-enable             Write files but do not enable/start services.
  -h, --help              Show this help.
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
HOST="0.0.0.0"
PORT="8080"
WEB_HOST="0.0.0.0"
WEB_PORT="5173"
MQTT_BROKER="127.0.0.1"
MQTT_PORT="1883"
PUBLIC_BASE_URL=""
DATABASE_URL=""
SERVICE_USER="${SUDO_USER:-root}"
PYTHON_BIN="python3"
NPM_BIN="npm"
ENABLE_MOSQUITTO=1
ENABLE_SERVICES=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --root)
      ROOT="$2"
      shift 2
      ;;
    --host)
      HOST="$2"
      shift 2
      ;;
    --port)
      PORT="$2"
      shift 2
      ;;
    --web-host)
      WEB_HOST="$2"
      shift 2
      ;;
    --web-port)
      WEB_PORT="$2"
      shift 2
      ;;
    --mqtt-broker)
      MQTT_BROKER="$2"
      shift 2
      ;;
    --mqtt-port)
      MQTT_PORT="$2"
      shift 2
      ;;
    --public-base-url)
      PUBLIC_BASE_URL="$2"
      shift 2
      ;;
    --database-url)
      DATABASE_URL="$2"
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
    --npm)
      NPM_BIN="$2"
      shift 2
      ;;
    --no-mosquitto)
      ENABLE_MOSQUITTO=0
      shift
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

if [[ -z "${ROOT}" ]]; then
  echo "ERROR: --root is required." >&2
  usage >&2
  exit 1
fi

if [[ -z "${PUBLIC_BASE_URL}" ]]; then
  echo "ERROR: --public-base-url is required and must be reachable from edge machines." >&2
  exit 1
fi

if [[ ! -d "${ROOT}" ]]; then
  echo "ERROR: NodeFlow root does not exist: ${ROOT}" >&2
  exit 1
fi

if [[ ! -f "${ROOT}/cloud/server/app.py" ]]; then
  echo "ERROR: cloud server app not found under ${ROOT}" >&2
  exit 1
fi

if [[ ! -f "${ROOT}/cloud/web/package.json" ]]; then
  echo "ERROR: cloud web package.json not found under ${ROOT}" >&2
  exit 1
fi

if [[ -z "${DATABASE_URL}" ]]; then
  DATABASE_URL="sqlite:///${ROOT}/cloud/server/farm.db"
fi

install -d -m 0755 /etc/nodeflow

cat > /etc/nodeflow/cloud.env <<EOF
NODEFLOW_ROOT=$(quote_env "${ROOT}")
PYTHONPATH=$(quote_env "${ROOT}")
NF_CLOUD_DATABASE_URL=$(quote_env "${DATABASE_URL}")
NF_CLOUD_MQTT_BROKER=$(quote_env "${MQTT_BROKER}")
NF_CLOUD_MQTT_PORT=$(quote_env "${MQTT_PORT}")
NF_CLOUD_HTTP_SERVER_HOST=$(quote_env "${HOST}")
NF_CLOUD_HTTP_SERVER_PORT=$(quote_env "${PORT}")
NF_CLOUD_HTTP_PUBLIC_BASE_URL=$(quote_env "${PUBLIC_BASE_URL%/}")
EOF

cat > /etc/systemd/system/nodeflow-cloud-api.service <<EOF
[Unit]
Description=NodeFlow Cloud API
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
EnvironmentFile=/etc/nodeflow/cloud.env
WorkingDirectory=${ROOT}
ExecStart=${PYTHON_BIN} -m uvicorn cloud.server.app:app --host ${HOST} --port ${PORT}
Restart=always
RestartSec=3
KillSignal=SIGTERM

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/nodeflow-cloud-web.service <<EOF
[Unit]
Description=NodeFlow Cloud Web
After=network-online.target nodeflow-cloud-api.service
Wants=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
WorkingDirectory=${ROOT}/cloud/web
ExecStart=${NPM_BIN} run dev -- --host ${WEB_HOST} --port ${WEB_PORT}
Restart=always
RestartSec=3
KillSignal=SIGTERM

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload

if [[ "${ENABLE_SERVICES}" -eq 1 ]]; then
  if [[ "${ENABLE_MOSQUITTO}" -eq 1 ]]; then
    if systemctl list-unit-files mosquitto.service >/dev/null 2>&1; then
      systemctl enable mosquitto.service
      systemctl restart mosquitto.service
    else
      echo "WARN: mosquitto.service not found; install Mosquitto or use --no-mosquitto." >&2
    fi
  fi
  systemctl enable nodeflow-cloud-api.service nodeflow-cloud-web.service
  systemctl restart nodeflow-cloud-api.service
  systemctl restart nodeflow-cloud-web.service
fi

cat <<EOF
Installed NodeFlow Cloud LAN services.

Environment:
  /etc/nodeflow/cloud.env

Services:
  nodeflow-cloud-api.service
  nodeflow-cloud-web.service
  mosquitto.service (if available and not disabled)

Open:
  http://<cloud-box-lan-ip>:${WEB_PORT}

Edge machines should use:
  NF_MQTT_BROKER=<cloud-box-lan-ip>
  NF_MQTT_PORT=${MQTT_PORT}
  NF_HTTP_SERVER_URL=http://<cloud-box-lan-ip>:${PORT}
EOF
