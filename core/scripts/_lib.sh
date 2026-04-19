#!/usr/bin/env bash
# _lib.sh — Shared output library for all coding-os scripts
# Source this file: source "$(dirname "$0")/_lib.sh"
# Google Shell Style Guide + AWS CLI output patterns

info()  { echo "INFO: $*"; }
ok()    { echo "OK: $*"; }
warn()  { echo "WARN: $*" >&2; }
err()   { echo "ERROR: $*" >&2; exit 1; }
