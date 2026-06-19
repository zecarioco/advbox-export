#!/usr/bin/env bash
# Gera todos os assets do ícone a partir de packaging/icon-source.svg.
#
# Saída:
#   packaging/icons/icon-{16,24,32,48,64,128,256,512,1024}.png
#   packaging/icons/AdvBoxExport.ico                          (Windows, multi-res)
#   packaging/icons/AdvBoxExport.icns                         (macOS, só roda em macOS)
#   advbox_export/ui/icons/app-icon.png                       (256, embedded no Qt app)
#
# Pré-requisitos: ImageMagick (`convert`). No macOS, também `iconutil` (vem com Xcode CLI).
set -euo pipefail

cd "$(dirname "$0")/.."

SRC="packaging/icon-source.svg"
OUT="packaging/icons"
APP_ICON_DIR="advbox_export/ui/icons"

if ! command -v convert >/dev/null 2>&1; then
  echo "erro: ImageMagick (convert) não encontrado"
  exit 1
fi
if [[ ! -f "$SRC" ]]; then
  echo "erro: $SRC não existe"
  exit 1
fi

mkdir -p "$OUT" "$APP_ICON_DIR"

echo "→ gerando PNGs…"
for size in 16 24 32 48 64 128 256 512 1024; do
  convert -background none -resize ${size}x${size} "$SRC" "$OUT/icon-${size}.png"
done

echo "→ gerando ICO (Windows)…"
convert "$OUT/icon-16.png" "$OUT/icon-24.png" "$OUT/icon-32.png" \
        "$OUT/icon-48.png" "$OUT/icon-64.png" "$OUT/icon-128.png" \
        "$OUT/icon-256.png" "$OUT/AdvBoxExport.ico"

echo "→ copiando app-icon.png (Qt window icon, 256px)…"
cp "$OUT/icon-256.png" "$APP_ICON_DIR/app-icon.png"

if [[ "$(uname -s)" == "Darwin" ]] && command -v iconutil >/dev/null 2>&1; then
  echo "→ gerando ICNS (macOS)…"
  ICONSET="$OUT/AdvBoxExport.iconset"
  rm -rf "$ICONSET"
  mkdir -p "$ICONSET"
  cp "$OUT/icon-16.png"   "$ICONSET/icon_16x16.png"
  cp "$OUT/icon-32.png"   "$ICONSET/icon_16x16@2x.png"
  cp "$OUT/icon-32.png"   "$ICONSET/icon_32x32.png"
  cp "$OUT/icon-64.png"   "$ICONSET/icon_32x32@2x.png"
  cp "$OUT/icon-128.png"  "$ICONSET/icon_128x128.png"
  cp "$OUT/icon-256.png"  "$ICONSET/icon_128x128@2x.png"
  cp "$OUT/icon-256.png"  "$ICONSET/icon_256x256.png"
  cp "$OUT/icon-512.png"  "$ICONSET/icon_256x256@2x.png"
  cp "$OUT/icon-512.png"  "$ICONSET/icon_512x512.png"
  cp "$OUT/icon-1024.png" "$ICONSET/icon_512x512@2x.png"
  iconutil -c icns "$ICONSET" -o "$OUT/AdvBoxExport.icns"
  rm -rf "$ICONSET"
else
  echo "→ pulando ICNS (precisa de macOS com iconutil)"
fi

echo "✓ pronto. saída em $OUT/ e $APP_ICON_DIR/app-icon.png"
