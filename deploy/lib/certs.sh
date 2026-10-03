#!/usr/bin/env bash
# deploy/lib/certs.sh: CA and leaf certificate generation.
# Shared by devtools/setup-dev.sh and deploy/armctl.sh. Sourced, never executed.
# Needs deploy/lib/common.sh loaded first. Callers set ARM_CERTS_DIR.

# Create the internal CA (EC P-384, 10 years) unless it already exists.
ensure_ca() {
    mkdir -p "${ARM_CERTS_DIR}"
    local ca_key="${ARM_CERTS_DIR}/arm-ca.key"
    local ca_crt="${ARM_CERTS_DIR}/arm-ca.crt"
    if [[ -f "$ca_key" && -f "$ca_crt" ]]; then
        arm_say "CA already exists; reusing"
        return 0
    fi
    arm_say "generating CA (EC P-384, 10y)"
    run_quiet openssl ecparam -name secp384r1 -genkey -noout -out "$ca_key"
    chmod 400 "$ca_key"
    run_quiet openssl req -x509 -new -nodes -key "$ca_key" -sha384 -days 3650 \
        -subj "/CN=ARM v3 Local CA" \
        -addext "basicConstraints=critical,CA:TRUE" \
        -addext "keyUsage=critical,keyCertSign,cRLSign" \
        -addext "subjectKeyIdentifier=hash" \
        -out "$ca_crt"
    chmod 444 "$ca_crt"
}

# make_leaf <name> [extra SAN ...]: issue a leaf signed by the CA. The name is
# always a DNS SAN; each extra SAN is an IP when it looks like one, DNS otherwise.
# Keys are 440 and group-owned by ARM_PGID so a stack whose PUID differs from
# the user who ran the installer can still read them.
make_leaf() {
    local name="$1"; shift
    local extra_sans=("$@")
    local key="${ARM_CERTS_DIR}/${name}.key"
    local csr="${ARM_CERTS_DIR}/${name}.csr"
    local crt="${ARM_CERTS_DIR}/${name}.crt"
    local ext="${ARM_CERTS_DIR}/${name}.ext"
    local san="DNS:${name}" s
    for s in "${extra_sans[@]:-}"; do
        [[ -z "$s" ]] && continue
        if [[ "$s" =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]]; then
            san+=",IP:${s}"
        else
            san+=",DNS:${s}"
        fi
    done
    arm_say "issued leaf: ${name} (SANs: ${san})"
    # Clear any earlier 0440/0444 files so openssl can overwrite.
    rm -f "$key" "$crt"
    run_quiet openssl ecparam -name prime256v1 -genkey -noout -out "$key"
    chmod 440 "$key"
    chgrp "${ARM_PGID:-$(id -g)}" "$key" 2>/dev/null || true
    run_quiet openssl req -new -key "$key" -subj "/CN=${name}" -out "$csr"
    cat > "$ext" <<EOF
subjectAltName = ${san}
extendedKeyUsage = serverAuth, clientAuth
EOF
    run_quiet openssl x509 -req -in "$csr" -CA "${ARM_CERTS_DIR}/arm-ca.crt" \
        -CAkey "${ARM_CERTS_DIR}/arm-ca.key" -CAcreateserial \
        -out "$crt" -days 3650 -sha384 -extfile "$ext"
    chmod 444 "$crt"
    rm -f "$csr" "$ext"
}
