#!/usr/bin/env bash
# Generate the internal CA and per-service leaves for the v3 walking skeleton.
# Replaces v3/install.sh until the real installer lands.
#
# Usage:  bash v3/devtools/bootstrap-certs.sh
# Outputs certs under v3/certs/ (bind-mounted by v3/docker-compose.yml).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
V3_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
CERT_DIR="${V3_DIR}/certs"

mkdir -p "${CERT_DIR}"
chmod 700 "${CERT_DIR}"
cd "${CERT_DIR}"

CA_KEY="arm-ca.key"
CA_CRT="arm-ca.crt"

if [[ ! -f "${CA_KEY}" ]]; then
    echo "generating CA (EC P-384, 10y)..."
    openssl ecparam -name secp384r1 -genkey -noout -out "${CA_KEY}"
    chmod 400 "${CA_KEY}"
    openssl req -x509 -new -nodes -key "${CA_KEY}" -sha384 -days 3650 \
        -subj "/CN=ARM v3 Local CA" \
        -addext "basicConstraints=critical,CA:TRUE" \
        -addext "keyUsage=critical,keyCertSign,cRLSign" \
        -addext "subjectKeyIdentifier=hash" \
        -out "${CA_CRT}"
    chmod 444 "${CA_CRT}"
else
    echo "CA already exists; reusing."
fi

mkleaf() {
    local name="$1"
    shift
    local extra_sans=("$@")
    local key="${name}.key"
    local csr="${name}.csr"
    local crt="${name}.crt"
    local ext="${name}.ext"

    echo "issuing leaf: ${name} (extra SANs: ${extra_sans[*]:-none})"

    openssl ecparam -name prime256v1 -genkey -noout -out "${key}"
    chmod 400 "${key}"

    openssl req -new -key "${key}" -subj "/CN=${name}" -out "${csr}"

    local san_line="DNS:${name}"
    for s in "${extra_sans[@]:-}"; do
        [[ -z "$s" ]] && continue
        san_line+=",DNS:${s}"
    done

    cat > "${ext}" <<EOF
subjectAltName = ${san_line}
extendedKeyUsage = serverAuth, clientAuth
EOF

    openssl x509 -req -in "${csr}" -CA "${CA_CRT}" -CAkey "${CA_KEY}" \
        -CAcreateserial -out "${crt}" -days 3650 -sha384 \
        -extfile "${ext}"
    chmod 444 "${crt}"

    rm -f "${csr}" "${ext}"
}

# arm-ui is the only listening service the browser talks to directly.
# Phase 13 (installer) will auto-detect the host's LAN hostname; today we
# hardcode `localhost` plus `hostname -f` so a browser pointed at either
# https://localhost:8081 or https://<host>:8081 doesn't trip a SAN mismatch.
HOST_FQDN="$(hostname -f 2>/dev/null || hostname || echo localhost)"

mkleaf arm-backend
mkleaf arm-db
mkleaf arm-ripper-sr0
mkleaf arm-ui localhost "${HOST_FQDN}"

cat <<EOF

done — next steps:
  cp ${V3_DIR}/.env.example ${V3_DIR}/.env
  # edit POSTGRES_PASSWORD and ARM_SERVICE_TOKEN to generated values, e.g.:
  #   openssl rand -hex 24   # for POSTGRES_PASSWORD
  #   openssl rand -hex 32   # for ARM_SERVICE_TOKEN
  docker compose -f ${V3_DIR}/docker-compose.yml up -d --build
EOF
