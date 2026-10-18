#!/bin/bash
# Play an audio file in the background with afplay (non-blocking).
# Usage: play-audio.sh FILE [RATE]   (RATE 0.50-1.50, default 1)
file="$1"
rate="${2:-1}"
if [ -z "$file" ] || [ ! -f "$file" ]; then
  echo "找不到音频文件：$file" >&2
  exit 1
fi
# Stop any previous playback so sounds don't overlap.
pkill -x afplay 2>/dev/null
# -q 1 selects the high-quality algorithm for rate-scaled playback.
nohup afplay -r "$rate" -q 1 "$file" >/dev/null 2>&1 &
