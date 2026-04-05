#!/usr/bin/env bash

set -euo pipefail

ACTION="${1:-install}"
ADDON_NAME="vertex_color_tool"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SOURCE_DIR="$REPO_ROOT/$ADDON_NAME"

detect_blender_version() {
    if [[ -n "${BLENDER_VERSION:-}" ]]; then
        printf '%s\n' "$BLENDER_VERSION"
        return
    fi

    local blender_root="$HOME/Library/Application Support/Blender"
    if [[ ! -d "$blender_root" ]]; then
        echo "Could not find $blender_root" >&2
        exit 1
    fi

    find "$blender_root" -mindepth 1 -maxdepth 1 -type d -exec basename {} \; | sort -V | tail -n 1
}

BLENDER_VERSION_DETECTED="$(detect_blender_version)"
TARGET_DIR="$HOME/Library/Application Support/Blender/$BLENDER_VERSION_DETECTED/scripts/addons"
TARGET_LINK="$TARGET_DIR/$ADDON_NAME"

if [[ ! -d "$SOURCE_DIR" ]]; then
    echo "Expected add-on package at $SOURCE_DIR" >&2
    exit 1
fi

case "$ACTION" in
    install)
        mkdir -p "$TARGET_DIR"
        if [[ -L "$TARGET_LINK" || -e "$TARGET_LINK" ]]; then
            echo "Add-on already exists at $TARGET_LINK" >&2
            echo "Use '$0 relink' to replace it." >&2
            exit 1
        fi
        ln -s "$SOURCE_DIR" "$TARGET_LINK"
        printf 'Installed %s into Blender %s\n' "$ADDON_NAME" "$BLENDER_VERSION_DETECTED"
        printf 'Path: %s\n' "$TARGET_LINK"
        ;;
    relink)
        mkdir -p "$TARGET_DIR"
        rm -rf "$TARGET_LINK"
        ln -s "$SOURCE_DIR" "$TARGET_LINK"
        printf 'Re-linked %s into Blender %s\n' "$ADDON_NAME" "$BLENDER_VERSION_DETECTED"
        printf 'Path: %s\n' "$TARGET_LINK"
        ;;
    uninstall)
        if [[ -L "$TARGET_LINK" || -e "$TARGET_LINK" ]]; then
            rm -rf "$TARGET_LINK"
            printf 'Removed %s from Blender %s\n' "$ADDON_NAME" "$BLENDER_VERSION_DETECTED"
            printf 'Path: %s\n' "$TARGET_LINK"
        else
            printf 'Nothing to remove at %s\n' "$TARGET_LINK"
        fi
        ;;
    *)
        echo "Usage: $0 [install|relink|uninstall]" >&2
        exit 1
        ;;
esac
