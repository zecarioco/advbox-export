#!/usr/bin/env bash
# Bump da versão no pyproject.toml, commit, tag v<versão> e push.
# Uso: ./scripts/release.sh 0.1.1
#
# Pré-requisitos:
#   - working tree limpo (sem mudanças não comitadas)
#   - branch atual = master
#   - remote 'origin' configurado
#
# O CI (.github/workflows/build.yml) dispara automaticamente ao receber a tag
# e publica uma release no GitHub com os 3 artefatos anexados.
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "uso: $0 <versão>   (ex: 0.1.1)"
  exit 1
fi

VERSAO="$1"

# Formato semver simples: X.Y.Z, opcionalmente -rc1, -beta, etc.
if ! [[ "$VERSAO" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9.]+)?$ ]]; then
  echo "erro: versão inválida '$VERSAO' — use formato X.Y.Z (ex: 0.1.1, 1.0.0-rc1)"
  exit 1
fi

TAG="v$VERSAO"

cd "$(dirname "$0")/.."

# Sanidade: working tree limpo
if [[ -n "$(git status --porcelain)" ]]; then
  echo "erro: working tree sujo — comita ou estasha antes de cortar a release"
  git status --short
  exit 1
fi

# Sanidade: na master
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
if [[ "$BRANCH" != "master" && "$BRANCH" != "main" ]]; then
  echo "erro: branch atual é '$BRANCH' — releases saem da master/main"
  exit 1
fi

# Sanidade: tag não existe
if git rev-parse "$TAG" >/dev/null 2>&1; then
  echo "erro: tag $TAG já existe"
  exit 1
fi

# Sanidade: master atualizada em relação ao remote
git fetch origin "$BRANCH" --quiet
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse "origin/$BRANCH")
if [[ "$LOCAL" != "$REMOTE" ]]; then
  echo "erro: $BRANCH local divergente do origin/$BRANCH — sync antes"
  exit 1
fi

echo "→ versão atual no pyproject.toml:"
grep '^version' pyproject.toml

echo "→ bumpando pra $VERSAO…"
# Substitui a linha 'version = "X.Y.Z"' do [project] preservando aspas.
sed -i.bak -E "s/^version = \".*\"/version = \"$VERSAO\"/" pyproject.toml
rm -f pyproject.toml.bak

echo "→ nova linha no pyproject.toml:"
grep '^version' pyproject.toml

git add pyproject.toml
git commit -m "chore: release $TAG"
git tag -a "$TAG" -m "Release $TAG"

echo
echo "→ pronto pra push. confirma?"
echo "    branch:  $BRANCH"
echo "    tag:     $TAG"
echo "    commit:  $(git rev-parse --short HEAD)"
read -r -p "[y/N] " RESP
if [[ "$RESP" != "y" && "$RESP" != "Y" ]]; then
  echo "abortado. desfaz com:"
  echo "    git tag -d $TAG"
  echo "    git reset --hard HEAD~1"
  exit 1
fi

git push origin "$BRANCH"
git push origin "$TAG"

echo
echo "✓ release $TAG empurrada."
echo "→ acompanhe o build em: $(git remote get-url origin | sed -E 's#(git@github.com:|https://github.com/)([^/]+/[^/.]+)(\.git)?#https://github.com/\2/actions#')"
