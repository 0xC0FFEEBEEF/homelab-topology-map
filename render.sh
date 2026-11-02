#!/usr/bin/env bash
# Render each poster-*.html to a 2x PNG (e.g. 3360 px wide for the network map) for Reddit.
set -euo pipefail
cd "$(dirname "$0")"
python3 build.py > /tmp/homelab-map-sizes.txt
cat /tmp/homelab-map-sizes.txt
while read -r file size; do
    w=${size%x*}; h=${size#*x}
    png="${file%.html}.png"
    google-chrome-stable --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=2 \
        --window-size="$w,$h" --virtual-time-budget=8000 --default-background-color=000000ff \
        --screenshot="$PWD/$png" "file://$PWD/$file" 2>/dev/null
    echo "wrote $png"
done < /tmp/homelab-map-sizes.txt
