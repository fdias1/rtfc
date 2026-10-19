#!/usr/bin/env bash
# Gera o áudio de referência (TTS do macOS, voz Luciana) a partir de reference.txt.
# Saídas (não versionadas): out/ref_clean.wav e out/ref_noisy.wav (ruído rosa a ~ -25 dB).
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p out/parts
# Só a Luciana: as vozes Eddy/Flo do macOS têm pronúncia ruim e inflam o WER.
voices=(Luciana)
i=0
: > out/parts/list.txt
while IFS= read -r line; do
  [ -z "$line" ] && continue
  v=${voices[$((i % ${#voices[@]}))]}
  say -v "$v" -o "out/parts/$i.aiff" "$line"
  ffmpeg -v error -y -i "out/parts/$i.aiff" -af "apad=pad_dur=0.6" -ar 16000 -ac 1 "out/parts/$i.wav"
  echo "file '$i.wav'" >> out/parts/list.txt
  i=$((i + 1))
done < reference.txt
ffmpeg -v error -y -f concat -safe 0 -i out/parts/list.txt -c copy out/ref_clean.wav
ffmpeg -v error -y -i out/ref_clean.wav -f lavfi -i "anoisesrc=color=pink:amplitude=0.04:sample_rate=16000" \
  -filter_complex "[0][1]amix=inputs=2:duration=first:normalize=0" -ar 16000 -ac 1 out/ref_noisy.wav
ffprobe -v error -show_entries format=duration -of csv=p=0 out/ref_clean.wav
