#!/usr/bin/env bash
# deploy/install/banner.sh: the banner `armctl install` opens with.
# Sourced by deploy/armctl.sh after ui.sh.

# The art is drawn with Unicode block characters, so it is shown only where it
# renders: a terminal at least BANNER_WIDTH columns wide, in a UTF-8 locale.
# Anywhere else (a narrow or non-UTF-8 terminal, a pipe, a log) a one-line
# title stands in. The release version is centred underneath either way.
BANNER_WIDTH=86
BANNER_ART="$(cat <<'ART'
                            ███████████
                     ████████         ████████
                 ███
              ████               ███  █   █ █████  ███  █   █  ███  █████ ███  ███
            ███                 █ ░░█ █░  █░ ░█░░░█ ░░█ ██ ██░█ ░░█  ░█░░░ █░░█ ░░░
          ██                    █████░█░░ █░░ █░░░█░ ░█░█░█ █░█████░  █░░░░█░░█░ ░░░
        ██                      █░░░█░█░░ █░░ █░░ █░░ █░█░░░█░█░░░█░░ █░░  █░░█░░
      ███                       █░░░█░░███ ░░ █░░  ███ ░█░░ █░█░░░█░░ █░░ ███░ ███
     █                           ░░  ░░ ░░░ ░  ░░   ░░░ ░░░  ░░░░  ░░  ░░  ░░░  ░░░
    █                             ░   ░  ░░░    ░    ░░░  ░   ░ ░   ░   ░   ░░░  ░░░
    █
  █                      ████████████        ████  ███ ████  ████  ███ █   █  ███
 █                   █ ██           ███      █░░░█  █░░█░░░█ █░░░█  █░░██  █░█ ░░░
                    █    ███████████   ██    ████░░ █░░████░░████░░ █░░█░█ █░█░ ██░
█                  █  ██████     █████  ██   █░░█░ ░█░░█░░░░ █░░░░ ░█░░█░░██░█░░ █░
                     ████           ████ ██  █░░░█░███░█░░░░░█░░░░░███░█░░ █░░███ ░░
█                  █████             ████ █   ░░  ░ ░░░ ░░    ░░    ░░░ ░░  ░░ ░░░ ░
█                 █████               ███ █    ░   ░ ░░░ ░     ░     ░░░ ░   ░  ░░░
█                 █████               █████
█                  ████               █████  █   █  ███   ███  █   █ ███ █   █ █████
█                 █ ████             ████    ██ ██░█ ░░█ █ ░░░ █░  █░ █░░██  █░█░░░░░
█                  █ █████         █████ █   █░█ █░█████░█░ ░░░█████░░█░░█░█ █░████░░░
 █                 ██  ███████████████  ██   █░░░█░█░░░█░█░░   █░░░█░░█░░█░░██░█░░░░
 ██                 ███  ███████████  ██     █░░ █░█░░░█░░███  █░░░█░███░█░░ █░█████░
  █                   ████         ████       ░░  ░░░░  ░░ ░░░  ░░  ░░░░░ ░░  ░░░░░░░
  ███                    ██████████            ░   ░ ░   ░  ░░░  ░   ░ ░░░ ░   ░ ░░░░░
   ██             █
     █
      ██          █                                        ███
       ██    █      █                                     ██
        ████ █                                          ███
          ████    █                                   ███
            ███████ █                              ████
               ████ █                           ████
                  ██████                    █████
                      ███████████ ███████████
                               ██████
ART
)"

banner_is_tty() { [[ -t 1 ]]; }

banner_cols() {
    local cols="${COLUMNS:-}"
    [[ -n "${cols}" ]] || cols="$(tput cols 2>/dev/null || true)"
    printf '%s' "${cols:-80}"
}

banner_utf8() {
    local locale="${LC_ALL:-${LC_CTYPE:-${LANG:-}}}"
    [[ "${locale,,}" == *utf-8* || "${locale,,}" == *utf8* ]]
}

# banner <version>
banner() {
    local version="$1" cols
    cols="$(banner_cols)"
    if banner_is_tty && banner_utf8 && [[ "${cols}" =~ ^[0-9]+$ ]] && (( cols >= BANNER_WIDTH )); then
        printf '\n%s\n\n%*s%s\n' "${BANNER_ART}" $(( (BANNER_WIDTH - ${#version}) / 2 )) '' "${version}"
    else
        printf '\nAutomatic Ripping Machine %s\n' "${version}"
    fi
}
