# AdvBox Export

App desktop para exportar atividades da AdvBox em XLSX e CSV, sem o limite de 1.000 registros do painel web. Funciona em Linux, macOS e Windows.

## Instalação

Baixe o pacote do seu sistema na página de [Releases](../../releases) mais recente:

| Sistema | Arquivo |
|---|---|
| Windows 10/11 | `AdvBoxExport-windows.zip` |
| macOS 12+ (Apple Silicon) | `AdvBoxExport-macos.dmg` |
| Linux | `AdvBoxExport-linux.tar.gz` |

### Windows
1. Extraia o `.zip` em qualquer pasta (ex.: `C:\Programas\AdvBoxExport`).
2. Crie um atalho de `AdvBoxExport.exe` na área de trabalho.

### macOS (Apple Silicon — M1/M2/M3/M4)
1. Abra o `AdvBoxExport-macos.dmg`. Uma janela com o ícone do app aparece.
2. Arraste **AdvBoxExport** para a pasta **Aplicativos**.
3. **Apenas na primeira vez:** clique com o **botão direito** no arquivo `primeiro-uso.command` (dentro da janela do DMG) e escolha **Abrir**. Confirme em "Abrir" no aviso do macOS. Vai aparecer um Terminal por um segundo e depois uma mensagem confirmando que o app foi liberado.
4. Pronto. Abra o **AdvBox Export** normalmente pelo Launchpad ou pela pasta Aplicativos.

> Por que esse passo? O app não é assinado por uma conta Apple paga (US$ 99/ano), então o macOS bloqueia a primeira execução por padrão. O script `primeiro-uso.command` libera o app de uma vez — não é necessário rodá-lo de novo, mesmo após atualizações.

### Linux
1. Extraia o `.tar.gz` em `~/Programas/`:
   ```bash
   mkdir -p ~/Programas && tar -xzf AdvBoxExport-linux.tar.gz -C ~/Programas/
   ```
2. Rode com `~/Programas/AdvBoxExport/AdvBoxExport`.
3. (Opcional) Crie atalho no menu de aplicativos.

## Primeira execução

Ao abrir pela primeira vez:

1. Vá em **Configurações → Editar configurações…**
2. Cole o **token AdvBox** (fornecido pela AdvBox aos integradores).
3. Salve.

O token fica gravado em arquivo de configuração do seu usuário e não precisa ser reinserido em futuras execuções.

## Como usar

1. Escolha o período (ou clique num dos atalhos: **Este mês**, **Mês passado**, **Este ano**, **Backfill completo** = últimos 6 anos).
2. Clique **Exportar agora**.
3. Acompanhe o progresso e o log. Quando concluir, o card **Histórico** mostra um botão para abrir o XLSX, o CSV e o log do run.

A API da AdvBox limita 30 requisições por minuto — exports grandes (ex.: 45.000 atividades) levam cerca de 25 minutos. O app respeita esse limite automaticamente e pode ser **cancelado a qualquer momento**; ao rodar de novo o mesmo período, ele retoma do ponto onde parou.

## Onde ficam os arquivos

| O quê | Linux | macOS | Windows |
|---|---|---|---|
| Configuração | `~/.config/AdvBoxExport/config.json` | `~/Library/Application Support/AdvBoxExport/config.json` | `%APPDATA%\MaldonadoAdv\AdvBoxExport\config.json` |
| Histórico (DB) | `~/.local/share/AdvBoxExport/advbox.db` | `~/Library/Application Support/AdvBoxExport/advbox.db` | `%LOCALAPPDATA%\MaldonadoAdv\AdvBoxExport\advbox.db` |
| Planilhas geradas | `~/.local/share/AdvBoxExport/exports/` | `~/Library/Application Support/AdvBoxExport/exports/` | `%LOCALAPPDATA%\MaldonadoAdv\AdvBoxExport\exports\` |

Pra abrir a pasta das planilhas: **Arquivo → Abrir pasta de exports**.

---

## Desenvolvimento

Pré-requisitos: Python 3.10+ e [uv](https://docs.astral.sh/uv/).

```bash
git clone <repo>
cd advbox-export
uv venv
uv pip install -e .
cp .env.example .env  # cole o ADVBOX_TOKEN nessa pasta pra rodar em dev
.venv/bin/python -m advbox_export
```

Em dev, o `.env` na raiz tem precedência sobre o `config.json` salvo na pasta do usuário — útil pra testar com tokens diferentes sem editar a configuração do app.

### Empacotamento manual

```bash
uv pip install -e ".[build]"
uv run pyinstaller --noconfirm --windowed --name AdvBoxExport --collect-all qt_material advbox_export/__main__.py
```

### Publicar release

```bash
git tag v0.1.0
git push --tags
```

O GitHub Actions builda nos três sistemas e publica o release com os artefatos anexados.
