#!/bin/sh
set -e

exec python3 -m pytest \
    --cov=pytools \
    --cov-report=term-missing \
    --cov-fail-under="${1:-80.0}"
