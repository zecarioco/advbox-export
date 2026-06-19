#!/usr/bin/env bash
# Empacota o build do PyInstaller (dist/AdvBoxExport/) em um .deb instalável
# via `sudo apt install ./AdvBoxExport-linux.deb` ou duplo clique no GNOME
# Software / KDE Discover.
#
# Saída: AdvBoxExport-linux.deb na raiz do projeto.
#
# Layout instalado:
#   /opt/AdvBoxExport/              binário e assets do PyInstaller
#   /usr/bin/advbox-export          wrapper que chama o binário
#   /usr/share/applications/        .desktop (faz aparecer na busca/Atividades)
#   /usr/share/icons/hicolor/...    ícones em várias resoluções
#
# Uso: ./packaging/linux/build-deb.sh <versão>
#   ex: ./packaging/linux/build-deb.sh 0.1.0
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "uso: $0 <versão>   (ex: 0.1.0)"
  exit 1
fi
VERSION="$1"
ARCH="amd64"

cd "$(dirname "$0")/../.."

if [[ ! -d "dist/AdvBoxExport" ]]; then
  echo "erro: dist/AdvBoxExport não existe — rode o PyInstaller antes"
  exit 1
fi

STAGE="dist/deb-staging"
rm -rf "$STAGE"

# ---- /opt/AdvBoxExport
mkdir -p "$STAGE/opt/AdvBoxExport"
cp -R dist/AdvBoxExport/. "$STAGE/opt/AdvBoxExport/"

# ---- /usr/bin/advbox-export (wrapper)
mkdir -p "$STAGE/usr/bin"
cat > "$STAGE/usr/bin/advbox-export" <<'EOF'
#!/bin/sh
exec /opt/AdvBoxExport/AdvBoxExport "$@"
EOF
chmod 755 "$STAGE/usr/bin/advbox-export"

# ---- /usr/share/applications/advbox-export.desktop
mkdir -p "$STAGE/usr/share/applications"
cat > "$STAGE/usr/share/applications/advbox-export.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=AdvBox Export
GenericName=Exportador AdvBox
Comment=Exportador de atividades da AdvBox em XLSX
Exec=/opt/AdvBoxExport/AdvBoxExport
Icon=advbox-export
Terminal=false
Categories=Office;Utility;
StartupWMClass=AdvBoxExport
EOF

# ---- /usr/share/icons/hicolor/<N>x<N>/apps/advbox-export.png
for size in 16 24 32 48 64 128 256 512; do
  ICON_DIR="$STAGE/usr/share/icons/hicolor/${size}x${size}/apps"
  mkdir -p "$ICON_DIR"
  cp "packaging/icons/icon-${size}.png" "$ICON_DIR/advbox-export.png"
done

# ---- DEBIAN/control
mkdir -p "$STAGE/DEBIAN"
# Tamanho instalado (KB), exigido por algumas ferramentas
INSTALLED_SIZE=$(du -sk "$STAGE/opt" "$STAGE/usr" | awk '{sum+=$1} END {print sum}')
cat > "$STAGE/DEBIAN/control" <<EOF
Package: advbox-export
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: ${ARCH}
Installed-Size: ${INSTALLED_SIZE}
Maintainer: Zé Estevão <joseestevaomarquesrocha@gmail.com>
Homepage: https://github.com/zecarioco/advbox-export
Description: Exportador de atividades da AdvBox em XLSX
 App desktop que replica as planilhas do painel da AdvBox sem o limite
 de 1.000 registros do painel web. Inclui filtro por destinatários,
 gerenciamento de grupos e retomada de exports cancelados.
EOF

# ---- post-install: atualiza cache de ícones e .desktop
cat > "$STAGE/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = "configure" ]; then
  if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q || true
  fi
  if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t /usr/share/icons/hicolor || true
  fi
fi
EOF
chmod 755 "$STAGE/DEBIAN/postinst"

cat > "$STAGE/DEBIAN/postrm" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = "remove" ] || [ "$1" = "purge" ]; then
  if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q || true
  fi
  if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t /usr/share/icons/hicolor || true
  fi
fi
EOF
chmod 755 "$STAGE/DEBIAN/postrm"

# ---- empacotamento
OUT="AdvBoxExport-linux.deb"
rm -f "$OUT"
dpkg-deb --build --root-owner-group "$STAGE" "$OUT"
echo "✓ gerado $OUT"
ls -lh "$OUT"
