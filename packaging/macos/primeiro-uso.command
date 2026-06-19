#!/bin/bash
# Libera o AdvBox Export do bloqueio inicial do macOS (Gatekeeper / quarantine).
# Dê um clique com o botão DIREITO neste arquivo e escolha "Abrir" para rodá-lo
# na primeira vez. Depois disso o AdvBox Export abre normalmente com duplo-clique.

# xattr -dr com.apple.quarantine /Applications/AdvBoxExport.app

set -e

APP="/Applications/AdvBoxExport.app"

if [ ! -d "$APP" ]; then
    osascript -e 'display dialog "AdvBox Export ainda não está instalado.\n\nArraste o ícone do AdvBox Export para a pasta Aplicativos (no DMG aberto) e rode este script de novo." with title "AdvBox Export — Primeiro uso" buttons {"OK"} default button "OK" with icon caution'
    exit 1
fi

xattr -dr com.apple.quarantine "$APP" 2>/dev/null || true

osascript -e 'display dialog "Pronto! O AdvBox Export está liberado.\n\nA partir de agora você pode abri-lo normalmente pelo Launchpad ou pela pasta Aplicativos." with title "AdvBox Export — Primeiro uso" buttons {"OK"} default button "OK" with icon note'
