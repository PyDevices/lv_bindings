#!/usr/bin/env bash
# Regenerate all binding targets, commit, and tag lv_bindings for the current
# LVGL submodule checkout.
#
# Typical workflow:
#   cd lvgl && git fetch --tags origin && git checkout v9.5.0 && cd ..
#   ./regenerate_all.sh --dry-run
#   ./regenerate_all.sh
#   git push origin HEAD --tags
#
# Tags follow LVGL major.minor with an lv_bindings patch counter, e.g. v9.5.0,
# v9.5.1, … for successive binding releases on the LVGL 9.5 line.
set -euo pipefail

LV_BINDINGS_DIR=$(cd "$(dirname "$0")" && pwd)
LVGL_DIR="$LV_BINDINGS_DIR/lvgl"
LVGL_H="$LVGL_DIR/lvgl.h"

usage() {
    cat <<'EOF'
Usage: ./regenerate_all.sh [--dry-run] [--no-commit] [--no-tag]

  --dry-run     Show planned tag and commit; do not regenerate, commit, or tag.
  --no-commit   Regenerate only; do not create a git commit.
  --no-tag      Regenerate (and commit unless --no-commit); do not create a tag.
EOF
}

DRY_RUN=0
NO_COMMIT=0
NO_TAG=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=1 ;;
        --no-commit) NO_COMMIT=1 ;;
        --no-tag) NO_TAG=1 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 1 ;;
    esac
    shift
done

if [[ "$DRY_RUN" -eq 1 && ( "$NO_COMMIT" -eq 1 || "$NO_TAG" -eq 1 ) ]]; then
    echo "Error: --dry-run cannot be combined with --no-commit or --no-tag" >&2
    exit 1
fi

if [[ ! -f "$LVGL_H" ]]; then
    echo "Error: $LVGL_H not found. Run: git submodule update --init lvgl" >&2
    exit 1
fi

read_lvgl_version() {
    local major minor patch version_file
    for version_file in "$LVGL_DIR/lv_version.h" "$LVGL_H"; do
        if [[ ! -f "$version_file" ]]; then
            continue
        fi
        major=$(grep -E '^#define LVGL_VERSION_MAJOR' "$version_file" | awk '{print $3}')
        minor=$(grep -E '^#define LVGL_VERSION_MINOR' "$version_file" | awk '{print $3}')
        patch=$(grep -E '^#define LVGL_VERSION_PATCH' "$version_file" | awk '{print $3}')
        if [[ -n "$major" && -n "$minor" && -n "$patch" ]]; then
            LVGL_MAJOR=$major
            LVGL_MINOR=$minor
            LVGL_PATCH=$patch
            LVGL_VERSION="${major}.${minor}.${patch}"
            return
        fi
    done
    echo "Error: could not read LVGL version from lv_version.h or lvgl.h" >&2
    exit 1
}

lvgl_git_label() {
    if git -C "$LVGL_DIR" describe --tags --exact-match >/dev/null 2>&1; then
        git -C "$LVGL_DIR" describe --tags --exact-match
    else
        git -C "$LVGL_DIR" describe --tags --always
    fi
}

next_bindings_tag() {
    local prefix="v${LVGL_MAJOR}.${LVGL_MINOR}."
    local latest next_patch
    latest=$(git -C "$LV_BINDINGS_DIR" tag -l "${prefix}*" | sort -V | tail -n 1)
    if [[ -z "$latest" ]]; then
        echo "v${LVGL_MAJOR}.${LVGL_MINOR}.0"
        return
    fi
    next_patch=$(("${latest##*.}" + 1))
    echo "v${LVGL_MAJOR}.${LVGL_MINOR}.${next_patch}"
}

read_lvgl_version
LVGL_LABEL=$(lvgl_git_label)
BINDINGS_TAG=$(next_bindings_tag)

planned_commit_message() {
    cat <<EOF
Regenerate bindings for LVGL ${LVGL_LABEL} (lv_bindings ${BINDINGS_TAG}).

LVGL API version: ${LVGL_VERSION}
EOF
}

planned_tag_message() {
    cat <<EOF
lv_bindings ${BINDINGS_TAG} — bindings for LVGL ${LVGL_MAJOR}.${LVGL_MINOR}.x

LVGL checkout: ${LVGL_LABEL}
LVGL API version: ${LVGL_VERSION}
EOF
}

show_release_plan() {
    local paths=(lvgl generated/lvmp.c generated/lvcp.c generated/lvpy.c)
    local would_commit=0

    echo "==> LVGL submodule: ${LVGL_LABEL} (API ${LVGL_VERSION})"
    echo "==> lv_bindings tag: ${BINDINGS_TAG}"
    echo
    echo "==> Paths staged on commit:"
    printf '    %s\n' "${paths[@]}"
    echo
    echo "==> Current changes (before regeneration):"
    if git -C "$LV_BINDINGS_DIR" diff --quiet -- "${paths[@]}" && \
       git -C "$LV_BINDINGS_DIR" diff --cached --quiet -- "${paths[@]}"; then
        echo "    (none — submodule pin and generated files match the index)"
    else
        git -C "$LV_BINDINGS_DIR" status --short -- "${paths[@]}" | sed 's/^/    /'
        would_commit=1
    fi
    echo
    echo "==> Planned commit message:"
    planned_commit_message | sed 's/^/    /'
    echo
    if git -C "$LV_BINDINGS_DIR" rev-parse "$BINDINGS_TAG" >/dev/null 2>&1; then
        echo "==> Tag: would fail — ${BINDINGS_TAG} already exists"
    else
        echo "==> Planned tag: ${BINDINGS_TAG}"
        echo "==> Planned tag message:"
        planned_tag_message | sed 's/^/    /'
    fi
    echo
    echo "Dry run: no files regenerated, no commit, no tag created."
    if [[ "$would_commit" -eq 0 ]]; then
        echo "Note: regeneration may still produce changes not visible until you run without --dry-run."
    fi
    echo
    echo "Run without --dry-run to publish:"
    echo "  ./regenerate_all.sh"
    echo "  git push origin HEAD --tags"
}

if [[ "$DRY_RUN" -eq 1 ]]; then
    show_release_plan
    exit 0
fi

echo "==> LVGL submodule: ${LVGL_LABEL} (API ${LVGL_VERSION})"
echo "==> lv_bindings tag: ${BINDINGS_TAG}"
echo

echo "==> Regenerate MicroPython bindings (lvmp.c)"
"$LV_BINDINGS_DIR/regenerate_lvmp.sh"
echo

echo "==> Regenerate CircuitPython bindings (lvcp.c)"
"$LV_BINDINGS_DIR/regenerate_lvcp.sh"
echo

echo "==> Regenerate CPython bindings (lvpy.c)"
"$LV_BINDINGS_DIR/regenerate_lvpy.sh"
echo

cd "$LV_BINDINGS_DIR"

COMMITTED=0
if [[ "$NO_COMMIT" -eq 0 ]]; then
    git add lvgl generated/lvmp.c generated/lvcp.c generated/lvpy.c
    if git diff --cached --quiet; then
        echo "==> No changes to commit (bindings already match LVGL ${LVGL_VERSION})"
    else
        git commit -m "$(planned_commit_message)"
        COMMITTED=1
        echo "==> Committed binding updates"
    fi
else
    echo "==> Skipping commit (--no-commit)"
fi

TAG_CREATED=0
if [[ "$NO_TAG" -eq 0 ]]; then
    if [[ "$NO_COMMIT" -eq 0 && "$COMMITTED" -eq 0 ]]; then
        echo "==> Skipping tag (no new commit)"
    else
        if git rev-parse "$BINDINGS_TAG" >/dev/null 2>&1; then
            echo "Error: tag ${BINDINGS_TAG} already exists" >&2
            exit 1
        fi
        git tag -a "$BINDINGS_TAG" -m "$(planned_tag_message)"
        TAG_CREATED=1
        echo "==> Created tag ${BINDINGS_TAG}"
    fi
else
    echo "==> Skipping tag (--no-tag)"
fi

echo
echo "Done."
if [[ "$TAG_CREATED" -eq 1 ]]; then
    echo "Push with:"
    echo "  git push origin HEAD --tags"
elif [[ "$COMMITTED" -eq 1 ]]; then
    echo "Push with:"
    echo "  git push origin HEAD"
fi
