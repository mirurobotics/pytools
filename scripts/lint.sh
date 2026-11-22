#!/bin/sh
set -e

FIX="--fix"
if [ "${LINT_FIX:-1}" = "0" ]; then
    FIX="--fix=false"
fi

exec python3 -m pytools lint $FIX
