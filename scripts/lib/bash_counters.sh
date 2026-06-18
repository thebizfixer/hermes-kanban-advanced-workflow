#!/usr/bin/env bash
# Safe counter increment under set -euo pipefail.
#
# Postfix ((var++)) returns exit status 1 when the value before increment was 0.
# In a script with set -e, that aborts even inside [[ cond ]] && ((var++)).
# Use bump NAME instead of ((NAME++)).

bump() {
    printf -v "$1" '%s' $((${!1:-0} + 1))
}
