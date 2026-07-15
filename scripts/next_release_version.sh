#!/usr/bin/env bash
# Compute the next lv_bindings release version.
#
# lv_bindings versions mirror the LVGL major.minor of the lvgl submodule, with
# an lv_bindings patch counter. The patch resets to 0 when the LVGL major or
# minor changes.
#   e.g. LVGL 9.5.x with last tag v9.5.5 -> 9.5.6 ; a new LVGL 9.6.x line -> 9.6.0
#
# Usage:
#   ./scripts/next_release_version.sh
#   ./scripts/next_release_version.sh --verbose

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_REPO="$(cd "$SCRIPT_DIR/.." && pwd)"
LVGL_DIR="$SOURCE_REPO/lvgl"

VERBOSE=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --verbose | -v)
            VERBOSE=1
            shift
            ;;
        --help | -h)
            sed -n '2,12p' "$0" | sed 's/^# \?//'
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

read_lvgl_version() {
    local version_file
    for version_file in "$LVGL_DIR/lv_version.h" "$LVGL_DIR/lvgl.h"; do
        [[ -f "$version_file" ]] || continue
        LVGL_MAJOR=$(grep -E '^#define LVGL_VERSION_MAJOR' "$version_file" | awk '{print $3}')
        LVGL_MINOR=$(grep -E '^#define LVGL_VERSION_MINOR' "$version_file" | awk '{print $3}')
        if [[ -n "${LVGL_MAJOR:-}" && -n "${LVGL_MINOR:-}" ]]; then
            return 0
        fi
    done
    echo "Error: could not read LVGL version from lvgl/lv_version.h or lvgl/lvgl.h" >&2
    echo "  Run: git submodule update --init lvgl" >&2
    exit 1
}

next_version() {
    local prefix="v${LVGL_MAJOR}.${LVGL_MINOR}."
    local latest remote_tag
    cd "$SOURCE_REPO"
    git fetch origin --tags 2>/dev/null || true
    remote_tag=$(
        git ls-remote --tags origin "${prefix}*" 2>/dev/null \
            | awk '{print $2}' \
            | sed 's|refs/tags/||' \
            | grep -v '\^{}$' \
            | sort -V \
            | tail -n 1
    )
    if [[ -n "$remote_tag" ]]; then
        latest=$remote_tag
    else
        latest=$(git tag -l "${prefix}*" | sort -V | tail -n 1)
    fi
    if [[ -z "$latest" ]]; then
        echo "${LVGL_MAJOR}.${LVGL_MINOR}.0"
    else
        echo "${LVGL_MAJOR}.${LVGL_MINOR}.$(("${latest##*.}" + 1))"
    fi
}

read_lvgl_version
VERSION="$(next_version)"

if [[ "$VERBOSE" -eq 1 ]]; then
    echo "LVGL API line: ${LVGL_MAJOR}.${LVGL_MINOR}.x"
    echo "Next version: ${VERSION}"
else
    echo "$VERSION"
fi
