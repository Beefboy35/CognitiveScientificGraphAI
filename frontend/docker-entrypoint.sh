#!/bin/sh
set -eu

ENV_JS_PATH="/usr/share/nginx/html/env.js"

{
  echo "window.__ENV__ = window.__ENV__ || {};"
  env | while IFS='=' read -r key value; do
    case "$key" in
      VITE_*)
        escaped=$(printf '%s' "$value" | sed 's/\\/\\\\/g; s/"/\\"/g')
        printf 'window.__ENV__["%s"] = "%s";\n' "$key" "$escaped"
        ;;
    esac
  done
} > "$ENV_JS_PATH"

exec nginx -g 'daemon off;'
