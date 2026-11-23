#!/bin/sh
set -e

FIX="--fix"
if [ "${LINT_FIX:-1}" = "0" ]; then
    FIX="--no-fix"
fi

exec python3 -m pytools lint $FIX
