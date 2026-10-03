#!/usr/bin/env bash
# deploy/lib/udev.sh: The host-wide udev rule and its installation.
# Shared by devtools/setup-dev.sh and deploy/armctl.sh. Sourced, never executed.
# Needs deploy/lib/common.sh loaded first.

# Prevent the host's udisks2/gvfs from auto-mounting optical drives ARM
# wants to drive. Without this, post-rip `eject` from the ripper
# container fails with EBUSY because the host mount holds /dev/srN.
# See docs/developers/architecture/06-deployment.md.
UDEV_RULE_PATH="/etc/udev/rules.d/99-arm-no-automount.rules"
build_udev_rule_content() {
    printf '# Managed by %s — do not edit by hand.\n' "${ARM_UDEV_MANAGED_BY}"
    cat <<'RULE'
# Disables host auto-mount for optical drives so an ARM ripper container can
# eject after a rip. Drives are hot-plugged and enrolled from the UI after
# install, so the rule is not scoped per drive: ARM owns the optical drives
# on this host. See docs/developers/architecture/06-deployment.md#host-side-auto-mount-must-be-disabled
SUBSYSTEM=="block", KERNEL=="sr[0-9]*", ENV{UDISKS_AUTO}="0"
RULE
}

# True when the installed rule already matches build_udev_rule_content. The
# rule is written with no trailing newline, so compare the same way.
udev_rule_current() {
    local desired
    desired="$(build_udev_rule_content)"
    [[ -r "${UDEV_RULE_PATH}" ]] && diff -q "${UDEV_RULE_PATH}" <(printf '%s' "${desired}") >/dev/null 2>&1
}

ensure_udev_rule() {
    if ! command -v udevadm >/dev/null 2>&1; then
        arm_say "udevadm not on PATH — skipping host udev rule (non-Linux host?)"
        return 0
    fi

    local desired
    desired="$(build_udev_rule_content)"

    if udev_rule_current; then
        arm_say "host udev rule already current at ${UDEV_RULE_PATH}"
        return 0
    fi

    if ! sudo -n true 2>/dev/null; then
        arm_say "sudo needs a password; to install the udev rule run:"
        arm_sub "    printf '%s' \"\$(cat <<'RULE'"
        printf '%s\n' "${desired}"
        arm_sub "RULE"
        arm_sub "    )\" | sudo tee ${UDEV_RULE_PATH}"
        arm_sub "    sudo udevadm control --reload-rules"
        arm_sub "    sudo udevadm trigger --subsystem-match=block"
        return 0
    fi

    arm_say "writing host udev rule at ${UDEV_RULE_PATH} (sudo)"
    printf '%s' "${desired}" | sudo tee "${UDEV_RULE_PATH}" >/dev/null
    sudo udevadm control --reload-rules
    sudo udevadm trigger --subsystem-match=block 2>/dev/null || sudo udevadm trigger
    arm_say "udev rule installed; udisks2 will skip auto-mount for ARM drives"
}
