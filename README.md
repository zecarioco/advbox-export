# AdvBox Export

App desktop para exportar atividades da AdvBox em XLSX, sem o limite de 1.000 registros do painel web. Funciona em Linux, macOS e Windows.

## Instalação

Baixe o pacote do seu sistema na página de [Releases](../../releases) mais recente:

| Sistema | Arquivo |
|---|---|
| Windows 10/11 | `AdvBoxExport-Setup.exe` |
| macOS 12+ (Apple Silicon) | `AdvBoxExport-macos.dmg` |
| Linux (Ubuntu/Debian) | `AdvBoxExport-linux.deb` |

### Windows
1. Abra `AdvBoxExport-Setup.exe` (duplo clique) e siga o assistente — instala em Program Files, cria atalho no Menu Iniciar e (opcional) na Área de Trabalho.
2. Abra **AdvBox Export** pelo Menu Iniciar ou digitando "AdvBox" na busca do Windows.

> O instalador não pede permissão de administrador (instala no perfil do usuário por padrão). Pra desinstalar: **Configurações → Apps → AdvBox Export → Desinstalar**.

### macOS (Apple Silicon — M1/M2/M3/M4)
1. Abra o `AdvBoxExport-macos.dmg`. Uma janela com o ícone do app aparece.
2. Arraste **AdvBoxExport** para a pasta **Aplicativos**.
3. **Apenas na primeira vez:** clique com o **botão direito** no arquivo `primeiro-uso.command` (dentro da janela do DMG) e escolha **Abrir**. Confirme em "Abrir" no aviso do macOS. Vai aparecer um Terminal por um segundo e depois uma mensagem confirmando que o app foi liberado.
4. Pronto. Abra o **AdvBox Export** normalmente pelo Launchpad ou pela pasta Aplicativos.

> Por que esse passo? O app não é assinado por uma conta Apple paga (US$ 99/ano), então o macOS bloqueia a primeira execução por padrão. O script `primeiro-uso.command` libera o app de uma vez — não é necessário rodá-lo de novo, mesmo após atualizações.

#### Se mesmo depois disso o macOS bloquear

Em versões mais novas do macOS, mesmo depois do `primeiro-uso.command` pode aparecer um aviso ao abrir o AdvBox Export pela primeira vez:

> **"AdvBoxExport.app" cannot be opened because the developer cannot be verified.**

Saída em 2 passos:

1. Clique em **Cancelar** no aviso.
2. Abra **Ajustes do Sistema → Privacidade e Segurança**. No fim da página, vai aparecer uma linha "AdvBoxExport.app foi bloqueado" com um botão **Abrir Mesmo Assim** (ou **Open Anyway**). Clique nele e confirme. Depois disso o app abre normal sempre.

Esse passo extra também só precisa ser feito uma vez.

### Linux (Ubuntu, Debian, Mint, Pop!_OS, etc.)
1. Instale o `.deb`:
   ```bash
   sudo apt install ./AdvBoxExport-linux.deb
   ```
   Ou: duplo clique no arquivo, que abre no Software Center / Discover.
2. Abra **AdvBox Export** pelas Atividades / menu de aplicativos (busca por "AdvBox").
   Ou no terminal: `advbox-export`.

> Pra desinstalar: `sudo apt remove advbox-export`.
> Pra Fedora/Arch/openSUSE: por enquanto não temos pacote nativo — abra uma issue se precisar.

## Primeira execução

Ao abrir pela primeira vez:

1. Vá em **Configurações → Editar configurações…**
2. Cole o **token AdvBox** (fornecido pela AdvBox aos integradores).
3. Salve.

O token fica gravado em arquivo de configuração do seu usuário e não precisa ser reinserido em futuras execuções.

## Como usar

1. **Nome do export** é preenchido automaticamente no formato `ADVBOX2026 - [02/06 - 02/09]` a partir do período escolhido. Você pode editar à mão; depois disso o app para de regerar.
2. **Período**: escolha manualmente nos campos *De* / *Até*, ou clique num atalho — **Este mês**, **Mês passado**, **Este ano**, **Backfill completo** (= últimos 6 anos).
3. **Opções avançadas**:
   - **Buscar Remetente** — preenche a coluna "Remetente" (autor da tarefa) fazendo 1 requisição extra por processo único no período. Custa ~2s por processo pelo rate limit da AdvBox; ex: 200 processos ≈ +7 min.
   - **Incluir comentários internos** — quando marcado, inclui tarefas com pontuação zero (comentários internos do escritório). Por padrão o app filtra essas — igual ao painel da AdvBox.
   - **Destinatários** — abre um diálogo pra escolher grupos cadastrados e/ou pessoas avulsas. Quem entrar em qualquer marcação aparece no export. Nada marcado = inclui todo mundo.
4. Clique **Exportar agora**.
5. Acompanhe o progresso e o log. Quando concluir, o card **Histórico** mostra botões pra abrir o XLSX e o log do run.

A API da AdvBox limita 30 requisições por minuto — exports grandes (ex.: 45.000 atividades) levam cerca de 25 minutos. O app respeita esse limite automaticamente e pode ser **cancelado a qualquer momento**; ao rodar de novo o mesmo período, ele retoma do ponto onde parou.

### O que entra no export

O export faz **duas passadas** pra cada período:

1. **Tarefas concluídas no período** (filtro `completed`) — relatório de produtividade
2. **Tarefas com prazo no período ainda em aberto** (filtro `deadline`) — backlog/atrasadas

Dedup por ID garante que tarefas que aparecem em ambas as passadas não se repitam. Isso significa que o export inclui tanto **o que foi entregue** quanto **o que ficou pra trás**, num único XLSX.

A coluna **"Status"** identifica cada caso:

| Status | Significado |
|---|---|
| **No prazo** | Concluída antes ou no prazo fatal |
| **Atrasada** | Concluída depois do prazo fatal |
| **Concluída** | Concluída, mas a tarefa não tinha prazo definido |
| **Em aberto** | Ainda não concluída, prazo no futuro (ou sem prazo) |
| **Em aberto atrasada** | Ainda não concluída, prazo já passou |

Pra cada tarefa, é emitida uma linha por destinatário. Tarefas em aberto mostram `Data Conclusão` vazia.

> **Custo de tempo**: como o export faz 2 queries por mês de período, o tempo total fica aproximadamente **2× o de antes**. Ex: backfill 6 anos que antes levava ~25 min agora leva ~50 min.

### Aba Grupos

A API da AdvBox não expõe a estrutura de equipes do painel, então o app permite cadastrar grupos manualmente. Cada grupo é uma lista de nomes da própria AdvBox (os mesmos 51 usuários cadastrados no `/settings.users`).

- **+ Novo grupo** — cria um grupo vazio e abre o seletor de pessoas pra popular.
- **⋯ → Editar pessoas** — abre o seletor de membros pra adicionar/remover gente.
- **⋯ → Renomear / Excluir grupo** — gerenciamento básico.
- **↻ Atualizar lista** (dentro do seletor) — força um `/settings.users` novo se você acabou de adicionar alguém na AdvBox e quer ver na lista.

Grupos cadastrados aqui ficam disponíveis no botão **Destinatários** da aba Export pra filtrar quem entra no XLSX.

## Onde ficam os arquivos

| O quê | Linux | macOS | Windows |
|---|---|---|---|
| Configuração | `~/.config/AdvBoxExport/config.json` | `~/Library/Application Support/AdvBoxExport/config.json` | `%APPDATA%\zecarioco\AdvBoxExport\config.json` |
| Histórico (DB) | `~/.local/share/AdvBoxExport/advbox.db` | `~/Library/Application Support/AdvBoxExport/advbox.db` | `%LOCALAPPDATA%\zecarioco\AdvBoxExport\advbox.db` |
| Planilhas geradas | `~/.local/share/AdvBoxExport/exports/` | `~/Library/Application Support/AdvBoxExport/exports/` | `%LOCALAPPDATA%\zecarioco\AdvBoxExport\exports\` |

Pra abrir a pasta das planilhas: **Histórico → Abrir pasta de exports**.

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
uv run pyinstaller \
  --noconfirm --windowed --name AdvBoxExport \
  --add-data "advbox_export/ui/styles.qss:advbox_export/ui" \
  --add-data "advbox_export/ui/styles_dark.qss:advbox_export/ui" \
  --add-data "advbox_export/ui/fonts:advbox_export/ui/fonts" \
  --add-data "advbox_export/ui/icons:advbox_export/ui/icons" \
  advbox_export/__main__.py
```

(No Windows substitua `:` por `;` nos `--add-data`.)

### Publicar release

O jeito recomendado:

```bash
./scripts/release.sh 0.1.0
```

O script bump o `pyproject.toml`, comita, cria a tag `v0.1.0` e dá push. O [GitHub Actions](.github/workflows/build.yml) então builda os 3 sistemas em paralelo e anexa os artefatos (`.zip`, `.dmg`, `.tar.gz`) numa release nova no GitHub.

Se quiser tagar à mão:

```bash
git tag v0.1.0
git push --tags
```

Pushes pra `master` sem tag também disparam o build (artefatos ficam no Actions por 14 dias, sem criar release).
