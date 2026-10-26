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
    # A run stopped half way can leave a 0400 key and no certificate behind;
    # openssl cannot overwrite that key.
    rm -f "$ca_key" "$ca_crt"
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

# san_is_ipv4 <value>: true for a dotted IPv4 address.
san_is_ipv4() {
    [[ "$1" =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]]
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
        if san_is_ipv4 "$s"; then
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

# ui_leaf_sans: the extra SANs for the UI leaf, one per line: localhost, the
# host name, and every non-loopback IPv4 address. Without the addresses a
# browser that trusts the CA still rejects https://<host-ip>:8081, the way
# other devices on the LAN reach the UI. Addresses are read at issue time;
# refresh_ui_leaf re-issues the leaf on `up` when the host has gained one.
ui_leaf_sans() {
    echo localhost
    hostname -f 2>/dev/null || hostname 2>/dev/null || echo localhost
    local ip
    for ip in $(hostname -I 2>/dev/null); do
        if san_is_ipv4 "$ip" && [[ "$ip" != 127.* ]]; then
            echo "$ip"
        fi
    done
}

# refresh_ui_leaf: re-issue the UI leaf when an address from ui_leaf_sans is
# missing from the certificate (a DHCP change, a new network card), so `up`
# covers a changed host without a reinstall. A certificate that names every
# current address is kept, also when it names addresses the host no longer
# has. Without a certificate the installer has not run; nothing is issued
# here. The new leaf is a new file behind arm-ui's single-file bind mount,
# so the running container keeps the old one until restart_ui_for_new_leaf
# (deploy/lib/lifecycle.sh) restarts it once the stack is up.
UI_LEAF_REISSUED=0
refresh_ui_leaf() {
    local crt="${ARM_CERTS_DIR}/arm-ui.crt" listed ui_sans san entry reason=""
    [[ -f "$crt" ]] || return 0
    # One SAN per line as openssl spells them: "DNS:nas.lan", "IP Address:10.0.0.5".
    listed="$(openssl x509 -in "$crt" -noout -ext subjectAltName 2>/dev/null \
        | tail -n +2 | tr ',' '\n' | sed 's/^[[:space:]]*//' || true)"
    mapfile -t ui_sans < <(ui_leaf_sans)
    if [[ -z "$listed" ]]; then
        reason="its addresses cannot be read"
    else
        for san in "${ui_sans[@]}"; do
            if san_is_ipv4 "$san"; then entry="IP Address:${san}"; else entry="DNS:${san}"; fi
            if ! grep -qxF "$entry" <<<"$listed"; then
                reason="${san} is not on it"
                break
            fi
        done
    fi
    [[ -n "$reason" ]] || return 0
    arm_say "re-issuing the UI certificate: ${reason}"
    make_leaf arm-ui "${ui_sans[@]}"
    # shellcheck disable=SC2034  # read by restart_ui_for_new_leaf in deploy/lib/lifecycle.sh
    UI_LEAF_REISSUED=1
}
