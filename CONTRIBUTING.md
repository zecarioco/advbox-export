# Contribuindo com o AdvBox Export

Guia para quem quer rodar o app em modo dev, gerar builds locais ou publicar uma release nova. Se você só quer usar o app, veja o [README](README.md).

## Rodando em dev

Pré-requisitos: Python 3.10+ e [uv](https://docs.astral.sh/uv/).

```bash
git clone git@github.com:zecarioco/advbox-export.git
cd advbox-export
uv venv
uv pip install -e .
cp .env.example .env  # cole o ADVBOX_TOKEN pra rodar em dev
.venv/bin/python -m advbox_export
```

Em dev, o `.env` na raiz tem precedência sobre o `config.json` do usuário — útil pra testar com tokens diferentes sem mexer na config do app.

## Empacotamento manual

O jeito normal é deixar o [GitHub Actions](.github/workflows/build.yml) gerar os pacotes automaticamente (veja "Publicar release" abaixo). Mas se quiser gerar localmente:

```bash
uv pip install -e ".[build]"
uv run pyinstaller \
  --noconfirm --windowed --name AdvBoxExport \
  --add-data "advbox_export/ui/styles.qss:advbox_export/ui" \
  --add-data "advbox_export/ui/styles_dark.qss:advbox_export/ui" \
  --add-data "advbox_export/ui/fonts:advbox_export/ui/fonts" \
  --add-data "advbox_export/ui/icons:advbox_export/ui/icons" \
  advbox_export/__main__.py
```

(No Windows substitua `:` por `;` nos `--add-data`.)

Pra empacotar como `.deb` (Linux): `bash packaging/linux/build-deb.sh <versão>` depois de rodar o pyinstaller.
Pra empacotar como `.exe` installer (Windows): rode o Inno Setup com `packaging/windows/AdvBoxExport.iss`.
Pra gerar o `.dmg` (macOS): veja o passo `Build (macOS)` no `.github/workflows/build.yml`.

## Regenerar os ícones

Os PNGs / `.ico` / `.icns` são gerados a partir de `packaging/icon-source.svg`. Pra recriar após editar o SVG:

```bash
bash packaging/generate-icons.sh
```

(Requer ImageMagick. O `.icns` só é gerado em macOS via `iconutil`.)

## Publicar release

O jeito recomendado:

```bash
./scripts/release.sh 0.1.2
```

O script bump o `pyproject.toml`, comita, cria a tag `v0.1.2` e dá push. O GitHub Actions builda os 3 sistemas em paralelo e anexa os artefatos (`.deb`, `.dmg`, `.exe`) numa release nova no GitHub.

Se quiser tagar à mão:

```bash
git tag v0.1.2
git push --tags
```

Pushes pra `master` sem tag também disparam o build (artefatos ficam no Actions por 14 dias, sem criar release).

## Estrutura do projeto

- `advbox_export/core/` — cliente HTTP, orquestração do export, persistência
- `advbox_export/ui/` — janela principal (PySide6/Qt), dialogs, tema
- `advbox_export/db.py` — histórico de exports em SQLite
- `packaging/` — SVG do ícone, scripts de empacotamento (`.deb`, `.iss` Inno Setup, `.command` macOS)
- `.github/workflows/build.yml` — build automatizado nos 3 SOs + release em tag `v*`
- `scripts/release.sh` — bump de versão + commit + tag + push
