# Instalação do Engine Local (Ollama) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fazer o Thero entregar na máquina do usuário o **mesmo estado de uma instalação manual do Ollama** — motor instalado como programa normal do usuário, modelo baixado na pasta padrão dele, acesso por HTTP em loopback e as variáveis de ambiente de sempre — sem nunca ser dono do processo do motor.

**Architecture:** Quatro módulos novos, pequenos, todos chamáveis pela ponte, com a fronteira de rede/processo **injetável** em cada um: `enginedata.py` (só evidência medida: URL, digest publicado, tamanho, assinante), `artifactcheck.py` (SHA-256 + assinatura Authenticode lida pelo próprio Windows, fail-closed), `download.py` (bytes num `.part` que só vira arquivo final depois do digest bater) e `engineinstall.py` (a máquina de estados `probe → plan → consent → execute`, que **observa** o motor por HTTP e escreve apenas a `$PROFILE` via `apply.py`). `localmodels.py` continua sendo o único cliente do Ollama e não ganha gestão de processo; o veto de loopback dele **não é tocado**. O provedor local não-Ollama (LM Studio) **já foi resolvido** na árvore pelo commit `0287c92` (`localmodels.guard_host` + `has_endpoint_path` + `authState "sem sonda"`): a Task 9 deste plano não reescreve isso, só trava o contrato por teste.

**Tech Stack:** Python 3.9+ stdlib apenas (`urllib`, `hashlib`, `subprocess`, `shutil`, `re`, `json`, `ast`, `pathlib`, `datetime`), pytest offline. Rede e subprocesso sempre passados por parâmetro ou monkeypatchados na costura pública do módulo (padrão real do repo: `localmodels.urlopen`). Exceção stdlib única e declarada: abrir um filho de PowerShell para ler a assinatura Authenticode — stdlib não verifica Authenticode no Windows (Task 7).

**Branch:** `feat/gui-engine-bridge` no submódulo `thero`. Commits **locais**, nunca `main`, nunca `push`.

**Baseline:** a árvore está sendo editada por outros agentes enquanto este plano é escrito e executado (`python -m pytest tests/ -q` deu **416 passed** no início desta sessão de planejamento e **444 passed / 13 failed** às 02:2x, com trabalhos em curso). Por isso a cadeia de contagem abaixo é escrita em função de `B`, o baseline **medido por você na Task 0**, e não de um número fixo. Onde está escrito `B + 41`, leia `pytest -q` e confira que o total subiu exatamente 41 desde a Task 0.

> **Correção de baseline na hora de executar (2026-09-28, depois deste plano ser
> escrito).** A suíte da ponte andou: `22ea931` + `5fcc3b7` + `b4bb7ec` +
> `0287c92` levaram a medição real para **442 passed**, e a Task 6b do plano da
> ponte (`--config`/`limits`, ainda não executada) acrescenta mais 15. As
> contagens "acumulada: NNN" abaixo continuam valendo como **delta** desta
> tarefa para a seguinte; o ponto de partida de cada executor é `python -m
> pytest tests/ -q` rodado ali, não o número impresso aqui. **Já aplicado:** a
> cadeia abaixo foi reescrita como `B + k` e a Task 0 é onde `B` é medido
> (junto com as falhas que já estavam na árvore, que não são deste plano).

---

## 1. Espinha dorsal não-negociável (palavra do dono, 2026-09-28)

> "EU DISSE QUE QUERO INSTALAR A PORRA DO OLLAMA E O MODELO, E USAR ELE, COMO SE O USUARIO TIVESSE INSTALADO MANUALMENTE NA MAQUINA E PASSADO OS DADOS DE ACESSO! ELE NAO VAI 'SUBIR' JUNTO COM O NOSSO PROGRAMA/SERVIÇO!"

1. **Instalar = deixar a máquina no estado de instalação manual.** Ollama como programa normal do usuário, modelo na pasta padrão dele. Nada de "portable do Thero", nada de pasta nossa, nada de binário embutido no payload, nada de copie-e-cole do executável para dentro do app.
2. **O ciclo de vida é do Ollama.** Start-up no login/serviço **dele**, portas **dele**, atualização **dele**. Nosso programa **nunca** é dono do processo: nunca spawnamos `ollama serve`, nunca matamos, nunca reiniciamos, nunca dependemos da nossa janela estar aberta. Thero fechado, IA no ar.
3. **Acesso pós-instalação é idêntico ao de quem configurou na mão:** HTTP em loopback (`localmodels.py` já é só isso) + `ATHENA_OLLAMA_HOST`/`ATHENA_OLLAMA_MODEL` e `SENTINEL_OLLAMA_HOST`/`SENTINEL_OLLAMA_MODEL`, escritas por `apply.profile_env_block`.
4. **Download com transparência:** avisar tamanho e pedir **um clique** antes de baixar qualquer coisa. Não é veto, é consentimento. E não usar "privacidade" como argumento contra instalar modelo local — é justamente ela que a instalação garante.
5. **Motor já existe na máquina → parar e perguntar.** Não silenciar a instalação que o usuário fez na mão.

### 1.1 Emenda do dono, posterior à citação acima (2026-09-28, segunda rodada)

A frase citada no item 2 diz "nunca reiniciamos". Ela é **mais antiga** que a
palavra seguinte do dono sobre o mesmo assunto: *"precisamos apenas checar o
status e iniciar ou mesmo reiniciar caso necessario (o ollama)"*. A regra não é
"nunca tocar no processo" — é **"não ser o pai dele"**. O que continua proibido,
e o plano não negocia: hospedar o motor, mantê-lo vivo (watcher, retry em
background, thread de monitoramento), subir junto com a nossa janela, matar por
nome de imagem, e instalar sem avisar tamanho + um clique.

O que passa a ser **permitido com gatilho explícito**: iniciar um motor que
está no ar de fora quando o usuário pede (ou quando um clique dele precisa do
motor caído), e reiniciar quando a configuração exigir, avisando antes. Nesses
dois casos o filho sai **desanexado**, sem pipe, sem `wait` nosso de
supervisão, sem guardar o objeto `Popen` — fechar o Thero não derruba o motor,
que é exatamente o contrário do nosso `--serve`.

**Onde isso mora, e por que não briga com este plano:** o ciclo de vida sob
demanda foi implementado no plano da ponte, no módulo **`engineproc.py`**
(`engine-start`/`engine-restart`, Task 8 Step 4D de
`2026-09-22-gui-engine-bridge.md`). Este plano continua sendo o dono de
**instalar e baixar**; nenhum módulo daqui passa a gerir processo, e a trava
`assert_not_lifecycle` abaixo vale **para os módulos deste plano**
(`enginedata`/`artifactcheck`/`download`/`engineinstall`) — que é o
escopo que ela já tem hoje. Quem executar a Task 11 não precisa afrouxar nada:
`["ollama", "serve"]` continua banned **aqui**, e é o `engineproc.py` do outro
plano que tem o caminho consentido.


**A linha do plano que torna o item 2 inafastável em código** é `engineinstall.assert_not_lifecycle()` (Task 11): **toda** linha de comando que o módulo gera passa por ela **antes** de virar processo, e um argv contendo `serve`/`start`/`stop`/`restart`/`kill`/`schtasks`/`reg add`/`sc create` levanta `OwnershipError`. Ela é amarrada por teste na Task 11 (item 3), na Task 12 (item 12) e na varredura AST da Task 13 (item 5). O docstring do módulo repete a regra em uma frase: *"O Thero NUNCA inicia, para, reinicia nem mantém o Ollama: apenas observa a porta por HTTP, com paciência."*


### 1.1 Conflito vivo encontrado na árvore (lido em 2026-09-28, às 02:2x)

Enquanto este plano era escrito, apareceu na árvore um arquivo **não commitado** de
outro trabalho: `src/thero/engineproc.py` (+ `tests/test_engineproc.py`, + a constante
`OLLAMA_START_WAIT` em `src/thero/settings.py`). Ele expõe `start()` e `restart()` que
fazem `subprocess.Popen([binary, "serve"], creationflags=DETACHED_PROCESS | ...)`, com
o comentário *"Nos nao somos o servico que hospeda o motor"*.

**Isto choca com o item 2 da espinha dorsal acima**, que é literal: "ele não vai subir
junto com o nosso programa/serviço", e com a regra "nunca spawnamos `ollama serve`". Um
`Popen` desanexado nosso é o nosso programa iniciando o motor — com o pretexto de que o
processo fica órfão. Não é este plano que decide isso: **é a Pergunta 10 do dono.**

O que este plano faz com essa realidade:

- Nenhuma task daqui importa, chama ou copia `engineproc`. As Tasks 10-13 tratam o motor
  ausente/parado como **estado a reportar**, nunca a corrigir com spawn (Task 11,
  `wait_for_engine`: observar com paciência e pedir ao usuário que abra o Ollama).
- `engineinstall.assert_not_lifecycle()` continua recusando `serve` em qualquer argv
  gerado por nós — inclusive se alguém tentar "aproveitar" o `engineproc` dentro de
  `execute` (a Task 13 prova isso pela varredura AST do único ponto de subprocesso).
- Se o dono decidir que o start manual-assistido do `engineproc` é aceitável, isso entra
  no plano da ponte como decisão explícita dele, com a linha "nós não somos donos do
  processo" reescrita lá — **não** por uma emenda silenciosa neste plano.

---

## 2. Quem é dono do quê (tabela para o executor não extrapolar)

| Ação | **Fazemos** | **Não fazemos** |
|---|---|---|
| Descobrir o motor | `shutil.which("ollama")` + sonda HTTP loopback `localmodels.status()`; **ler** `HKCU\...\Run` e `Get-ScheduledTask` só para informar | escrever em serviço, tarefa agendada, registro ou start-up |
| Baixar o instalador | HTTPS na URL oficial **medida** (Task 1), para a pasta de trabalho do temp do usuário; conferir SHA-256 **publicado** (Task 5) e assinatura Authenticode; avisar tamanho + clique | embutir binário no payload, copiar exe para dentro do app, http://, rodar sem verificar, pinar a URL assinada do redirect (expira) |
| Instalar | abrir o `OllamaSetup.exe` baixado — filho de uma vez, que roda, instala e **morre** — e depois **esperar o motor responder por HTTP** | spawn de `ollama serve`; matar/reiniciar processo do motor; escolher porta; criar pasta de modelo; tocar em `~/.ollama/models` |
| Baixar modelo | `localmodels.pull()` (HTTP no motor **dele**), com tamanho anunciado e clique; progresso por callback | `ollama pull` como subprocesso, definir `OLLAMA_MODELS`, mover blob |
| Configurar acesso | `$env:ATHENA_OLLAMA_HOST/MODEL` + `$env:SENTINEL_OLLAMA_HOST/MODEL` na `$PROFILE` via `apply.apply_profile` (backup, merge, recusa) | env de máquina, service env, `.env` nosso, ler valor de chave (só presença) |
| Recuperação | **re-observar** a máquina (motor presente? modelo no `list`? config escrita?) e retomar o `.part` da descarga | state machine de instalação própria, arquivo de estado, lock, pidfile, "nossa janela precisa estar aberta" |
| Desinstalar | **informar** que remover o Ollama é ação do dono da máquina e apontar o nosso bloco na `$PROFILE` pelos marcadores | apagar Ollama, apagar modelo, `shutil.rmtree`, `os.remove` fora do `.part` temporário nosso |

---

## 3. Contexto real (medido/lido nesta máquina em 2026-09-28 — não presumir)

| Fato | Como foi verificado hoje |
|---|---|
| Baseline no início do planejamento **416 passed**; às 02:2x **444 passed, 13 failed** (outros agentes na árvore) → a contagem deste plano é relativa a `B`, medido na Task 0 | `python -m pytest tests/ -q` |
| Provedor local **não-Ollama já entregue** (`0287c92`): `localmodels.has_endpoint_path`, `localmodels.guard_host`, `authState "sem sonda"`; `guard_base` continua recusando caminho | `src/thero/localmodels.py:62-120`, `providers.py:195-215` |
| `system.process.stream_command` **já existe** (`b4bb7ec`) e produz `("out", linha)`/`("exit", código)` | `src/thero/system/process.py:75` |
| Por arquivo hoje: `test_providers.py` 59, `test_localmodels.py` 32, `test_apply.py` 38 | `pytest -q` por arquivo |
| `ollama` **não** está no PATH; `%LOCALAPPDATA%\Programs\Ollama` **não existe** | `shutil.which("ollama")` → `None` |
| **Mas** `~/.ollama/models` **existe**, com 8 arquivos e **13.671.200.219 bytes**; manifests de `qwen2.5/7b` e `qwen2.5-coder/14b` | `Path.home()/'.ollama'/'models'` |
| Estado "modelo presente, motor ausente" é **real** aqui → o plano tem de tratá-lo | dedução das duas linhas acima |
| A porta de entrada do instalador responde `200` e **redireciona** para um asset de release do GitHub com URL assinada que **expira** (`se=` na query) | `HEAD https://ollama.com/download/OllamaSetup.exe` via stdlib |
| `Content-Length` medido hoje: **1.571.115.536 bytes** (~1,46 GiB), `application/octet-stream` | mesma requisição |
| A release mais recente **publica `sha256sum.txt`** (1472 B) com a linha `4a6514323eb8c131f6c8bb651b4fe2edf5f1525f4fd8b84315ba20f1af3e210f  ./OllamaSetup.exe`; tag vista: `v0.34.4` | `api.github.com/repos/ollama/ollama/releases/latest` + download do asset |
| `Get-AuthenticodeSignature` devolve `Status` + `SignerCertificate.Subject` em um comando de uma linha (validado com `svchost.exe` → `Valid\|CN=Microsoft Windows, O=..., C=US`) | `powershell -NoProfile -NonInteractive -Command` |
| **Armadilha real 1:** com `-Command`, um argumento extra **não** binda em `$args[0]` — o PowerShell cola o resto na linha e o comando quebra (rc 1). A forma que funcionou: caminho **dentro** do script, em aspas simples com aspas dobradas (rc 0; tentar injetar com `'` no caminho não executou nada) | testado nesta sessão |
| **Armadilha real 2:** stdout/stderr do PowerShell nesta máquina nem sempre é UTF-8 (byte `0xc6` estourou `encoding="utf-8"`) → `errors="replace"` é obrigatório | testado nesta sessão |
| Espaço livre em `C:` hoje: **338,9 GB** de 952,8 GB | `shutil.disk_usage("C:/")` |
| `llama3.2` = 2.0 GB; `qwen3-coder-next` = **52 GB** (`:q8_0` 85 GB) — o default do Sentinel pesa 52 GB | páginas `ollama.com/library/llama3.2` e `.../qwen3-coder-next` |
| A doc do Windows cita `%LOCALAPPDATA%\Programs\Ollama`, `/DIR="..."`, modelos em `~/.ollama`/`OLLAMA_MODELS` e **não** documenta flag silenciosa nem mecanismo de start-up | `docs.ollama.com/windows` |
| `localmodels` é cliente HTTP puro: `normalize_base`, `_assert_loopback` (recusa **path**), `guard_base`, `list_models`, `pull`, `delete`, `status` → `{up, base, models, error}`; nenhuma gestão de processo | `src/thero/localmodels.py:47-283` |
| `apply.profile_env_block` escreve os dois pares; `_ollama_base` só casa `preset/id == "ollama"` → LM Studio não vaza para `ATHENA_OLLAMA_HOST` | `src/thero/apply.py:285-325` |
| Athena lê `ATHENA_OLLAMA_HOST` **sem validar host** (default `http://localhost:11434`, modelo `llama3.2`) → o veto tem de morar em quem escreve | `athena/src/athena/settings.py:45-72` |
| Sentinel veta non-loopback no próprio código e hoje declara "quem prove o motor é o usuário ou o Genesis" | `sentinel/src/sentinel/settings.py:255-283`, `local_model.py:82-96` |
| `shutil.disk_usage` / `shutil.which` são as únicas leituras de disco/PATH de que o plano precisa (já usados em `envreport.py`) | `src/thero/envreport.py:34-35` |
| **Conflito lido hoje:** `src/thero/engineproc.py` (não commitado, de outro trabalho) faz `Popen([binary, "serve"], DETACHED_PROCESS)` em `start()`/`restart()`; `OLLAMA_START_WAIT = 6` foi acrescentado a `settings.py` por ele | lido nesta sessão (seção 1.1 e Pergunta 10) |
| O plano do time (`2026-09-28-registro-de-equipe.md`) referencia este trabalho como `plan: onboarding-motor-local` — **este arquivo é ele** | seção "Pré-requisito referenciado" daquele plano |

**O que este plano muda na premissa do Sentinel:** apenas o fato de que alguém pode ter instalado o motor por nós (com clique do dono). A validação de segurança do Sentinel continua válida e **não é tocada**: nenhum arquivo fora de `thero/` é modificado por este plano.

---

## 4. Dependência declarada: a ponte GUI↔motor está sendo escrita

O plano `docs/superpowers/plans/2026-09-22-gui-engine-bridge.md` está em execução por outro agente **enquanto este é escrito** (as Tasks 7-12 dele). **Não edite esse arquivo e não escreva em `bridge.py`, `gui/*`, `build.ps1`, `system/process.py`.**

- A única superfície destinada à ponte é a função do motor: `engineinstall.execute(plan_out, *, consent, progress, workdir, cfg, deps)`, com `progress(step: str, detail: str, percent: int)` (percent `-1` = desconhecido) e `consent(plan_out) -> bool`. Ela é **síncrona** e devolve um relatório JSON-safe. A barra de progresso visual, o worker e o cancelamento moram na ponte e **não** são deste plano: é exatamente por isso que `execute` nunca imprime e nunca assume janela aberta.
- A Task 11 também entrega `engineinstall.stream_model(name, *, base="", emit=None)`, que produz `("out", linha)` / `("exit", código)` — a mesma forma que `system.process.stream_command` entrega hoje (a Task 7 da ponte foi embarcada em `b4bb7ec`), de propósito: a ponte junta os dois fluxos no painel de terminal sem adaptar nada. Nenhuma das duas funções usa `print()`.
- Consequência prática: **nenhuma task daqui depende da ponte para passar.** Se você sentir falta de um handler ao executar a Task 13, **pare e registre como dependência** na Pergunta 6 do dono; não escreva na ponte.
- Colisões conhecidas: `providers.py` e `localmodels.py` foram tocados pela ponte neste mesmo dia (`0287c92`). Se uma task sua precisar mexer neles, confirme primeiro com `git status --short src/` que não há trabalho de outra pessoa pendente no arquivo.

---

## 5. Regras que valem para cada task

1. **Stdlib apenas.** A única exceção é "não existe lib stdlib para Authenticode no Windows", resolvida com um filho de PowerShell de uma linha (Task 7), justificada no docstring do módulo.
2. **Python 3.9:** `from __future__ import annotations`; sem `match`; sem `tomllib`; sem `Path.write_text(newline=...)`.
3. **Proibido `print()`** em função chamável pela ponte (stdout é o canal JSON). Provado por varredura AST na Task 13.
4. **Proibido ler valor de variável de ambiente** (só presença). O host do motor vem do **provedor salvo em `config.json`** e passa por `localmodels.guard_base`; `OLLAMA_HOST`/`OLLAMA_MODELS` **não** são lidos. Provado por teste na Task 10.
5. **Ollama loopback only, sem exceção.** `localmodels._assert_loopback` não é afrouxado em nenhuma task.
6. **Testes offline e determinísticos:** download/subprocesso/redação injetáveis; nada escreve fora de `tmp_path`; nenhum teste marca `live`.
7. **Módulos novos em `src/` 100% ASCII** (docstring incluída), linhas ≤ 79 chars. Texto que atravessa a ponte não tem acento. Testes podem ter acento (padrão do repo).
8. **Commit local** só com o "ok" explícito do usuário; nunca `main`, nunca `push`.

Rodar testes sempre de `c:/Users/anthe/.myscripts/thero`: `python -m pytest tests/ -q`.

**Contagem:** as "Expected" abaixo são escritas como `B + k`, com `B` medido na Task 0. Verifique `k` (o delta), não o total absoluto: outros agentes estão somando testes a esta árvore enquanto você executa.

---

## 6. File Structure

**Cria:**

- `thero/src/thero/enginedata.py` — evidência medida, com data e fonte: URL da porta de entrada, API da release, nome do artefato, digest conhecido-bom, assinante esperado, tabela de tamanho por modelo, flags do instalador, piso de disco. `checksums_url(tag)` valida a tag. **Sem rede, sem processo, sem disco.**
- `thero/src/thero/artifactcheck.py` — `sha256_of`, `parse_checksums` (formato publicado `sha  ./nome`), `read_latest_tag`, `ps_quote`/`sign_script`/`sign_command`/`signature` (Authenticode, fail-closed, runner injetável), `verdict`, `check`.
- `thero/src/thero/download.py` — `to_file`: https obrigatório, nome validado, `.part` dentro do workdir, `os.replace` só depois do digest bater, teto de bytes, pulo-idempotente quando o arquivo íntegro já existe.
- `thero/src/thero/engineinstall.py` — o provisionamento: `assert_not_lifecycle`/`OwnershipError`, `probe`, `has_model`, `plan`, `release_info`, `launch_installer`, `wait_for_engine`, `percent_from_line`, `ensure_model`, `stream_model`, `consumer_env_targets`, `resolve_profile`, `write_consumer_env`, `execute`, `advice`.
**Nenhum arquivo de estado**: a idempotência vem de re-observar a máquina (ver seção "Idempotência", Task 12).
- Testes: `tests/test_enginedata.py`, `tests/test_artifactcheck.py`, `tests/test_download.py`, `tests/test_providers_local_non_ollama.py`, `tests/test_engineinstall_plan.py`, `tests/test_engineinstall_steps.py`, `tests/test_engineinstall_execute.py`, `tests/test_engineinstall_invariants.py`.

**Modifica:**

- `thero/tests/test_providers_local_non_ollama.py` — Task 9 **não** muda `src/`: o ramo não-Ollama já foi entregue (`0287c92`). A task trava por teste o contrato que o onboarding consome.
- `thero/README.md` — uma seção "Motor local: instalar é uma coisa, ter o processo é outra". Task 14.
- Este arquivo — seção 12 (evidência das Tasks 1-5).

**Não toca (deliberadamente):** `localmodels.py` (nem `_assert_loopback`, nem o contrato de `pull`), `envreport.py`, `apply.py`, `presets.py`, `config.py`, `settings.py`, `bridge.py`/`gui/*`/`build.ps1` (zona da ponte), `docs/superpowers/plans/2026-09-22-gui-engine-bridge.md`, e qualquer arquivo fora de `thero/`.

---

### Task 0: Medir o baseline `B` (a árvore está em movimento)

Outros agentes estão escrevendo nesta árvore agora (o plano da ponte e o do time). Nenhuma contagem deste documento faz sentido sem você medir o ponto de partida **depois** de pegar o estado atual.

- [ ] **Step 1: Atualizar e medir**

```bash
git status --short
git log --oneline -3
python -m pytest tests/ -q
```

Anotar `B` = o número de `passed` da última linha. **Se houver `failed` na árvore agora**, anote também a lista: falha que já estava aqui não é deste plano, e o portão final (Task 15) só exige que o seu trabalho não tenha **acrescentado** falha nenhuma.

- [ ] **Step 2: Não commitar nada**

Nada nesta task muda arquivo. Se `git status --short` já mostrar modificação de `src/thero/*` que não é sua, **não commite junto**: avise o dono na hora (ele ficará horas ausente) e trabalhe por cima sem tocar naqueles arquivos.

---

## Fase A — Descoberta (Tasks 1-5): você não sabe, então meça

Regra da fase: **nada** do que vai para o código vem da minha ou da sua memória. Cada task abaixo tem o comando exato e o que anotar. As Tasks 6-9 consomem o resultado na seção 12. Rodar na máquina do dono. Comandos que **baixam bytes** estão marcados: exigem o clique explícito do dono antes de executar (item 4 da espinha dorsal).

### Task 1: Descobrir a fonte real do instalador (URL, nome, tamanho, redirecionamento)

`HEAD` não baixa corpo — não precisa de clique.

**Files:**
- Modify: `docs/superpowers/plans/2026-09-28-instalacao-do-engine-local.md` (seção 12, bloco E1)

- [ ] **Step 1: Listar os candidatos Windows na página oficial**

```bash
python - <<'PY'
import re, urllib.request
for page in ("https://ollama.com/download",
             "https://ollama.com/download/windows"):
    html = urllib.request.urlopen(page, timeout=30).read().decode(
        "utf-8", "replace")
    print("==", page)
    for href in sorted(set(re.findall(r'href="([^"]+)"', html))):
        if any(k in href.lower() for k in ("win", ".exe", ".msi", ".ps1")):
            print("  ", href)
PY
```

Anotar **cada** candidato exatamente como apareceu (hoje: `https://ollama.com/download/OllamaSetup.exe` e `https://ollama.com/install.ps1`).

- [ ] **Step 2: Medir o candidato escolhido**

```bash
python - <<'PY'
import urllib.request
url = "https://ollama.com/download/OllamaSetup.exe"   # do Step 1
with urllib.request.urlopen(
        urllib.request.Request(url, method="HEAD"), timeout=60) as r:
    print("status", r.status)
    print("final-prefix", r.geturl().split("?")[0][:120])
    print("len", r.headers.get("Content-Length"))
    print("type", r.headers.get("Content-Type"))
    print("expira?", "se=" in r.geturl() or "sig=" in r.geturl())
PY
```

Anotar: status, `Content-Length` **em bytes**, `Content-Type`, prefixo do URL final e se a query traz `se=`/`sig=`. Hoje: `200`, `1571115536`, `application/octet-stream`, redirecionando para `release-assets.githubusercontent.com/github-production-release-asset/...` **com expiração**.

- [ ] **Step 3: Conclusão obrigatória do Step 2**

Se `expira? = True`: o plano **não** pina o asset assinado; pina a porta de entrada + o digest publicado (Task 5). Escrever essa conclusão em E1 com uma frase.

- [ ] **Step 4: Escrever E1 na seção 12 e commitar**

```bash
git add docs/superpowers/plans/2026-09-28-instalacao-do-engine-local.md
git commit -m "docs(plano-engine): E1 fonte do instalador medida na maquina"
```

---

### Task 2: Descobrir o que a fonte **publica** sobre integridade

A pergunta não é "tem hash?", é "que arquivo, com que formato, para que artefato, nesta release".

**Files:**
- Modify: este arquivo (seção 12, bloco E2)

- [ ] **Step 1: Confirmar que a página/doc não publicam digest**

```bash
python - <<'PY'
import urllib.request
for url in ("https://ollama.com/download",
            "https://ollama.com/download/windows",
            "https://docs.ollama.com/windows"):
    body = urllib.request.urlopen(url, timeout=30).read().decode(
        "utf-8", "replace").lower()
    print(url, "->", [k for k in ("sha256", "checksum", "digest", "md5")
                      if k in body])
PY
```

- [ ] **Step 2: Procurar o digest na release do GitHub e conferir o formato**

```bash
python - <<'PY'
import json, re, urllib.request
api = "https://api.github.com/repos/ollama/ollama/releases/latest"
data = json.loads(urllib.request.urlopen(api, timeout=30).read().decode())
print("tag", data.get("tag_name"), "id", data.get("id"))
assets = data.get("assets", [])
for a in assets:
    print(a["name"], a["size"])
names = [a["name"] for a in assets]
wanted = [n for n in names if "sha256" in n.lower() or "sum" in n.lower()]
print("candidatos de digest:", wanted)
if wanted:
    text = urllib.request.urlopen(
        "https://github.com/ollama/ollama/releases/download/%s/%s"
        % (data["tag_name"], wanted[0]), timeout=30
    ).read().decode("utf-8", "replace")
    print(repr(text[:200]))
    for line in text.splitlines():
        if "OllamaSetup" in line:
            print("PUBLISHED:", line.strip())
            print("FORMATO OK?", bool(re.match(
                r"^[0-9a-fA-F]{64}\s+\*?\.?[/\\]?OllamaSetup\.exe$",
                line.strip())))
PY
```

Anotar: a tag, **todos** os nomes de asset, o nome do arquivo de digest (se houver), a linha exata do artefato Windows e se o formato bate `sha  ./nome` (é esse parser que a Task 7 implementa). Hoje: `sha256sum.txt` (1472 B) existe; linha do Windows `4a6514...210f  ./OllamaSetup.exe`.

- [ ] **Step 3: Se não existir digest publicado, registrar a alternativa verificável**

Se (e somente se) o Step 2 não achar arquivo de digest, anotar em E2: *"nenhum digest publicado nesta release → a trava passa a ser só a assinatura Authenticode (Task 5) + o digest medido gravado na ledger"*, e **não** inventar URL de terceiro como fonte de checksum.

- [ ] **Step 4: Escrever E2 na seção 12 e commitar**

```bash
git add docs/superpowers/plans/2026-09-28-instalacao-do-engine-local.md
git commit -m "docs(plano-engine): E2 digest publicado verificado"
```

---

### Task 3: Descobrir a tecnologia do instalador e quais flags são defensáveis

**Baixar o arquivo exige o clique do dono** (são ~1,5 GB, medidos na Task 1). Antes de rodar o comando abaixo, diga em voz alta ao dono: tamanho, URL exata e que o arquivo **não** será executado nesta task.

**Files:**
- Modify: este arquivo (seção 12, bloco E3)

- [ ] **Step 1: Baixar o artefato na pasta de trabalho (sem instalá-lo)**

```bash
mkdir -p "$TEMP/thero-engine-probe"
curl -L --proto-redir =https -o "$TEMP/thero-engine-probe/OllamaSetup.exe" \
  https://ollama.com/download/OllamaSetup.exe
certutil -hashfile "%TEMP%\thero-engine-probe\OllamaSetup.exe" SHA256
```

`--proto-redir =https` não é enfeite: a URL redireciona (Task 1) e um redirect para `http://` trocaria o transporte no meio da descarga. Depois que a Task 8 existir, o mesmo download pode ser refeito pelo código do produto — o que serve de teste vivo dele:

```bash
python - <<'PY'
from pathlib import Path
from thero import download
work = Path.home() / "AppData" / "Local" / "Temp" / "thero-engine-probe"
out = download.to_file(
    "https://ollama.com/download/OllamaSetup.exe", "OllamaSetup.exe", work)
print(out["ok"], out["bytes"], out["sha256"], out["reason"])
PY
```

Anotar: bytes recebidos vs. `Content-Length` da Task 1 e o SHA-256 medido. **O `.exe` baixado não é executado nesta task** (a Task 3 para aqui; instalar é a Task 12, com clique).

- [ ] **Step 2: Ler a assinatura do arquivo baixado (não instala nada)**

Rodar pelo Python com argv em lista: no PowerShell de uma linha pelo bash, o `|` dentro da aspa do script é armadilha de quoting, e o argv em lista não tem shell no meio (é a mesma forma que `artifactcheck.sign_command` usa na Task 7):

```bash
python - <<'PY'
import subprocess
from pathlib import Path
target = (Path.home() / "AppData" / "Local" / "Temp" / "thero-engine-probe"
          / "OllamaSetup.exe")
quoted = "'" + str(target).replace("'", "''") + "'"
script = ("$s = Get-AuthenticodeSignature -LiteralPath " + quoted
          + "; $s.Status.ToString() + '|' + $s.SignerCertificate.Subject")
out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive",
                      "-Command", script],
                     capture_output=True, text=True, encoding="utf-8",
                     errors="replace", timeout=120, shell=False)
print("rc", out.returncode)
print("saida", (out.stdout or "").strip())
PY
```

Forma da saída (medida hoje com `svchost.exe`): `Valid|CN=Microsoft Windows, O=Microsoft Corporation, L=Redmond, S=Washington, C=US`. Anotar a linha `Status|Subject` **completa** do artefato do Ollama: é o `Subject` que vira `EXPECTED_PUBLISHER` na Task 6 — hoje o plano só tem a substring `"Ollama"`, que é uma **hipótese** até este Step rodar.

- [ ] **Step 3: Inspeção estática do artefato (tecnologia do empacotador)**

```bash
python - <<'PY'
from pathlib import Path
path = Path.home() / "AppData" / "Local" / "Temp" / "thero-engine-probe"
data = (path / "OllamaSetup.exe").read_bytes()
print("bytes", len(data))
for marker in (b"Inno Setup Setup Data", b"Nullsoft", b"Windows Installer",
               b"MSI", b".text"):
    print(marker.decode("ascii", "replace"), "->", data.find(marker))
PY
```

Anotar os offsets. Marcador de Inno Setup ⇒ as flags `/VERYSILENT`, `/NORUN`, `/TASKS=noautostart` são **candidatas** (família Inno), não verdade.

- [ ] **Step 4: Procurar a documentação das flags na fonte do empacotador**

```bash
python - <<'PY'
import re, urllib.request
for topic in ("setupcmdline", "compilercmdline"):
    url = "https://jrsoftware.org/ishelp/index.php?topic=" + topic
    text = re.sub(r"<[^>]+>", " ", urllib.request.urlopen(
        url, timeout=30).read().decode("utf-8", "replace"))
    print("==", topic)
    for flag in ("/VERYSILENT", "/SILENT", "/NORUN", "/TASKS",
                 "/MERGETASKS", "/DIR", "/ALLUSERS", "/CURRENTUSER"):
        print("  ", flag, flag.lower() in text.lower())
PY
```

E perguntar à fonte primária se o Ollama documenta algo:

```bash
python - <<'PY'
import re, urllib.request
for url in ("https://docs.ollama.com/windows",
            "https://raw.githubusercontent.com/ollama/ollama/main/docs/windows.md"):
    text = re.sub(r"<[^>]+>", " ", urllib.request.urlopen(
        url, timeout=30).read().decode("utf-8", "replace")).lower()
    print("==", url)
    for flag in ("/verysilent", "/norun", "/tasks", "noautostart", "/dir"):
        print("  ", flag, flag in text)
PY
```

**Critério de decisão (escreva o resultado em E3):** só entra em `enginedata.INSTALLER_ARGS` uma flag que apareça **nas duas** fontes (empacotador **e** Ollama) ou que você tenha validado executando o instalador numa máquina descartável. Sem isso: `INSTALLER_ARGS = ()` — o assistente abre visível e o usuário clica, que é **exatamente** "instalação manual". Este é o default conservador do plano.

- [ ] **Step 5: Escrever E3 na seção 12 e commitar**

```bash
git add docs/superpowers/plans/2026-09-28-instalacao-do-engine-local.md
git commit -m "docs(plano-engine): E3 empacotador e flags verificados"
```

---

### Task 4: Descobrir o ciclo de vida na máquina (start-up, pastas, espaço)

**Leitura pura.** Estas consultas não escrevem em lugar nenhum — e **nenhuma task deste plano vai escrever nelas**.

**Files:**
- Modify: este arquivo (seção 12, bloco E4)

- [ ] **Step 1: Como o motor sobe sozinho — observar, nunca tocar**

```bash
reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Run"
```

```bash
python - <<'PY'
import shutil, subprocess
print("ollama no PATH:", shutil.which("ollama"))
out = subprocess.run(
    ["powershell", "-NoProfile", "-NonInteractive", "-Command",
     "Get-ScheduledTask | Where-Object { $_.TaskName -match 'Ollama' } "
     "| Select-Object -ExpandProperty TaskName"],
    capture_output=True, text=True, encoding="utf-8", errors="replace",
    timeout=30, shell=False)
print("tarefas agendadas:", (out.stdout or "").strip() or "nenhuma",
      "rc", out.returncode)
PY
```

Anotar: nome + alvo da chave de Run (se houver), tarefas agendadas, se `ollama` está no PATH e **onde**. Se o motor não estiver instalado, anotar `PENDENTE (motor ausente nesta maquina)`.

- [ ] **Step 2: Onde caem os modelos, nesta máquina**

```bash
python - <<'PY'
import os
from pathlib import Path
root = Path.home() / ".ollama" / "models"
print("dir:", root, "existe:", root.is_dir())
print("OLLAMA_MODELS presente no ambiente?", "OLLAMA_MODELS" in os.environ)
blobs = root / "blobs"
total = files = 0
if blobs.is_dir():
    for p in blobs.rglob("*"):
        if p.is_file():
            total += p.stat().st_size
            files += 1
print("blobs:", files, "arquivos,", total, "bytes")
manifests = root / "manifests"
if manifests.is_dir():
    for p in sorted(manifests.rglob("*")):
        if p.is_file():
            print("manifest:", p.relative_to(manifests))
PY
```

Anotar: caminho real, total de bytes, lista de manifests. Hoje: `13.671.200.219` bytes com `library/qwen2.5/7b` e `library/qwen2.5-coder/14b` **sem motor instalado** → o `plan()` da Task 10 precisa do estado "motor ausente, blobs presentes".

- [ ] **Step 3: Espaço livre no volume que recebe os blobs**

```bash
python - <<'PY'
import shutil
from pathlib import Path
usage = shutil.disk_usage(str(Path.home()))
print("total GB %.1f  free GB %.1f" % (usage.total / 2**30,
                                       usage.free / 2**30))
PY
```

Anotar `free` em bytes. Comparar com a soma da Task 5 **mais** o instalador da Task 1 **mais** `DISK_RESERVE_GIB`. Hoje em `C:` 338,9 GB livres.

- [ ] **Step 4: Confirmar a política de ambiente (só presença)**

```bash
python - <<'PY'
import os
for name in ("OLLAMA_HOST", "OLLAMA_MODELS", "OLLAMA_KEEP_ALIVE"):
    print(name, "presente?", name in os.environ)
PY
```

Anotar apenas **presença/ausência** — o plano proíbe ler valor (regra 4, seção 5): o host vem do provedor em `config.json`, não do ambiente.

- [ ] **Step 5: Escrever E4 na seção 12 e commitar**

```bash
git add docs/superpowers/plans/2026-09-28-instalacao-do-engine-local.md
git commit -m "docs(plano-engine): E4 ciclo de vida e disco medidos"
```

---

### Task 5: Descobrir o tamanho de cada modelo (e o que o dono aceita baixar)

Sem número medido, "avisar o tamanho" é chute — e o aviso é a única acomodação que o dono aceitou.

**Files:**
- Modify: este arquivo (seção 12, bloco E5)

- [ ] **Step 1: Tamanho anunciado, por tag, para os defaults dos consumidores**

```bash
python - <<'PY'
import re, urllib.request
for name in ("llama3.2", "qwen3-coder-next", "qwen2.5-coder"):
    url = "https://ollama.com/library/%s/tags" % name
    try:
        body = urllib.request.urlopen(url, timeout=30).read().decode(
            "utf-8", "replace")
    except Exception as exc:
        print(name, "ERR", type(exc).__name__, exc)
        continue
    text = re.sub(r"<[^>]+>", " ", body)
    print(name, sorted(set(re.findall(r"([0-9][0-9.]*\s*(?:GB|MB|TB))",
                                      text)))[:12])
PY
```

Anotar valor **por tag exata** (`llama3.2:latest`, `qwen3-coder-next:q4_K_M`, `qwen2.5-coder:14b`). Hoje: `llama3.2` 2.0 GB; `qwen3-coder-next` **52 GB** (`q8_0` 85 GB) — ou seja, o default documentado do Sentinel é um download de 52 GB, o que obriga a Pergunta 1 do dono.

- [ ] **Step 2: Comparar com o que já está na máquina**

```bash
python - <<'PY'
from pathlib import Path
root = Path.home() / ".ollama" / "models" / "manifests"
for p in sorted(root.rglob("*")) if root.is_dir() else []:
    if p.is_file():
        print(p.relative_to(root))
PY
```

Anotar quais defaults já existem como manifest (motor ausente ≠ modelo ausente).

- [ ] **Step 3: Formato da linha de progresso do pull (só com o motor de pé)**

```bash
PYTHONPATH=src python - <<'PY'
from thero import localmodels
import time
started = time.time()
for kind, line in localmodels.pull("llama3.2:1b"):
    print("%.1fs" % (time.time() - started), kind, repr(line)[:120])
    if kind == "exit":
        break
PY
```

`PYTHONPATH=src` porque `pythonpath = pytest.ini` so vale dentro do pytest (verificado hoje: sem ele, `import thero` falha fora da suíte). O prefixo de tempo e o que responde "primeira linha em quanto tempo", que e o dado que a tela de progresso precisa.

Anotar se as linhas trazem percentual (`NN %`) e se algum evento carrega `completed`/`total`. Sem motor na máquina, anotar `PENDENTE` — `percent_from_line` (Task 11) trata os dois casos e é testado com as duas formas. **Não** trocar o contrato de `localmodels.pull` para acrescentar campos: isso é decisão da ponte (Task 7 lá), não daqui.

- [ ] **Step 4: Escrever E5 na seção 12 e commitar**

```bash
git add docs/superpowers/plans/2026-09-28-instalacao-do-engine-local.md
git commit -m "docs(plano-engine): E5 tamanho de modelos medido"
```

---

## Fase B — Integridade e dados (Tasks 6-8)

### Task 6: `enginedata.py` — a evidência medida pinada em um lugar só

Só dados + uma validação de string. Se um valor aqui estiver errado, a tela de consentimento mente — por isso cada constante carrega a data e a task que a mediu. As Tasks 1-5 **atualizam** estes valores com a medição da máquina do dono.

**Files:**
- Create: `src/thero/enginedata.py`
- Test: `tests/test_enginedata.py`

- [ ] **Step 1: Escrever o teste que falha**

`tests/test_enginedata.py`:

```python
"""Os numeros do plano tem de existir, ter forma e nao ser inventados."""

import inspect
import re

import pytest

from thero import enginedata


def test_urls_are_https_and_ascii():
    for url in (enginedata.INSTALLER_URL, enginedata.RELEASE_API_URL,
                enginedata.CHECKSUMS_URL):
        assert url.startswith("https://")
        assert url.isascii()


def test_checksums_url_builds_for_a_tag():
    url = enginedata.checksums_url("v0.34.4")
    assert url.endswith("/" + enginedata.CHECKSUMS_NAME)
    assert "/v0.34.4/" in url


@pytest.mark.parametrize("tag", ["", "latest", "../x", "v1\nX",
                                 "a" * 80, None, 7])
def test_checksums_url_refuses_anything_else(tag):
    with pytest.raises(ValueError):
        enginedata.checksums_url(tag)


def test_pinned_values_have_the_documented_shape():
    assert re.match(r"^[0-9a-f]{64}$", enginedata.KNOWN_GOOD_SHA256)
    assert enginedata.KNOWN_GOOD_BYTES > 0
    assert enginedata.KNOWN_GOOD_TAG.startswith("v")
    assert re.match(r"^\d{4}-\d{2}-\d{2}$", enginedata.VERIFIED_ON)
    assert enginedata.EXPECTED_PUBLISHER.isascii()


def test_installer_args_carry_no_engine_lifecycle():
    # A Task 3 decide; ate la, () = assistente visivel (instalacao manual).
    for flag in enginedata.INSTALLER_ARGS:
        assert isinstance(flag, str)
        assert flag.upper() not in enginedata.FORBIDDEN_ARGS


def test_model_sizes_cover_the_consumer_defaults():
    for name in enginedata.CONSUMER_DEFAULTS:
        assert enginedata.MODEL_SIZE_GIB[name] > 0


def test_no_network_or_process_in_the_data_module():
    text = inspect.getsource(enginedata)
    for banned in ("subprocess", "urllib.request", "socket", "print("):
        assert banned not in text
```

- [ ] **Step 2: Rodar para ver falhar**

Run: `python -m pytest tests/test_enginedata.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'thero.enginedata'`

- [ ] **Step 3: Escrever o módulo**

`src/thero/enginedata.py`:

```python
"""Evidencia medida sobre a instalacao do motor local (Ollama).

Nada aqui e opiniao nem memoria: cada numero tem fonte e data, coletados
pelas tasks de descoberta do plano
docs/superpowers/plans/2026-09-28-instalacao-do-engine-local.md (E1-E5).
Trocar um valor sem re-medir e mentir para a tela de consentimento, e o
aviso de tamanho + um clique e a unica acomodacao que o dono aceitou.

A URL FINAL do asset do GitHub NAO e pinada: ela expira em minutos
(assinatura SAS com `se=`, medido na Task 1), entao pinamos a porta de
entrada estavel e conferimos o digest publicado na release corrente.

Este modulo nao faz rede, nao faz processo, nao faz disco: so dados e a
validacao de uma tag que virara trecho de URL.
"""

from __future__ import annotations

import re

# --- fonte do artefato (E1) ----------------------------------------------
INSTALLER_URL = "https://ollama.com/download/OllamaSetup.exe"
INSTALLER_NAME = "OllamaSetup.exe"
RELEASE_API_URL = "https://api.github.com/repos/ollama/ollama/releases/latest"
CHECKSUMS_NAME = "sha256sum.txt"
CHECKSUMS_URL = ("https://github.com/ollama/ollama/releases/download/"
                 "{tag}/" + CHECKSUMS_NAME)

# --- integridade (E2, E3) -------------------------------------------------
# Conhecido-bom da ultima medicao: referencia para comparar, nunca trava
# absoluta. A trava real e o digest publicado na release que baixarmos.
VERIFIED_ON = "2026-09-28"
VERIFIED_BY = "plano 2026-09-28-instalacao-do-engine-local, Tasks 1-3"
KNOWN_GOOD_TAG = "v0.34.4"
KNOWN_GOOD_SHA256 = (
    "4a6514323eb8c131f6c8bb651b4fe2edf5f1525f4fd8b84315ba20f1af3e210f"
)
KNOWN_GOOD_BYTES = 1571115536
# Subject esperado da assinatura Authenticode. A Task 3 Step 2 registra o
# Subject COMPLETO na secao 12; a trava e por substring porque o Subject vem
# como "CN=..., O=..., L=..., S=..., C=US".
EXPECTED_PUBLISHER = "Ollama"

# --- flags do instalador (E3) --------------------------------------------
# Somente flags documentadas pelo empacotador E confirmadas para este exe.
# Vazio = abrir o assistente visivel, que e literalmente "o usuario instalou
# na maquina dele". Nada de adivinhar /VERYSILENT.
INSTALLER_ARGS: tuple = ()
# Jamais passam pela trava do Task 11, mesmo se a E3 as documentar: mexem no
# ciclo de vida da maquina ou no processo de outra pessoa.
FORBIDDEN_ARGS = frozenset({
    "/RESTART", "/NORESTART", "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS",
    "/ALLUSERS", "/CANCEL", "/LOG",
})

# --- ciclo de vida: apenas texto de recusa (E4) ---------------------------
# O Thero NAO escreve em nada disto; cita para o usuario saber onde procurar.
AUTOSTART_KEY = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run"
BINARY_DIR = r"%LOCALAPPDATA%\Programs\Ollama"
MODEL_DIR = r"%USERPROFILE%\.ollama\models"

# --- modelos (E5) ---------------------------------------------------------
# GiB anunciados na biblioteca, por tag. O default do Sentinel e caro: por
# isso o consentimento e por nome, nao um "tudo ou nada".
MODEL_SIZE_GIB = {
    "llama3.2": 2.0,
    "llama3.2:1b": 1.3,
    "llama3.2:3b": 2.0,
    "qwen2.5-coder:14b": 9.3,
    "qwen3-coder-next": 52.0,
}
MODEL_SIZE_SOURCE = ("ollama.com/library/<nome>/tags, verificado em "
                     "2026-09-28 (Task 5)")
# O par que cada consumidor le hoje: athena/src/athena/settings.py:52-72 e
# sentinel/src/sentinel/settings.py:255-283.
CONSUMER_DEFAULTS = ("llama3.2", "qwen3-coder-next")

# --- disco (E4) -----------------------------------------------------------
DISK_RESERVE_GIB = 10.0
GIB = 1024 ** 3

_TAG = re.compile(r"v[0-9][A-Za-z0-9._-]{0,60}\Z")


def is_release_tag(tag: object) -> bool:
    """Forma de tag de release que pode virar trecho de URL.

    Publicado porque `artifactcheck.read_latest_tag` precisa da mesma regra:
    um satellite nao compoe o privado do vizinho (mesma logica que levou
    `localmodels` a expor `guard_base`).
    """
    return isinstance(tag, str) and _TAG.match(tag) is not None


def checksums_url(tag: object) -> str:
    """URL da lista de sumarizacoes de uma tag, com a tag validada.

    A tag vem da API e vira trecho de URL: sem validar, `../`, espaco ou
    quebra de linha virariam path/header injection na requisicao.
    """
    if not is_release_tag(tag):
        raise ValueError("tag de release inesperada: %r" % (tag,))
    return CHECKSUMS_URL.format(tag=tag)
```

- [ ] **Step 4: Rodar para ver passar**

Run: `python -m pytest tests/test_enginedata.py -q`
Expected: `13 passed` (6 funções de caso único + 7 casos de `test_checksums_url_refuses_anything_else`)

Run: `python -m pytest tests/ -q`
Expected: `B + 13` passed

- [ ] **Step 5: Commit local**

```bash
git add src/thero/enginedata.py tests/test_enginedata.py
git commit -m "feat(enginedata): evidencia medida da fonte do motor pinada num modulo so"
```

**Acumulado: B + 13.**

---

### Task 7: `artifactcheck.py` — saber o que você executou

Baixar executável da internet e rodar é o ponto de risco de cadeia de suprimentos do projeto. O mínimo honesto e verificável com stdlib é: **(a)** SHA-256 sempre medido e **exigido quando publicado** (a Task 2 provou que `sha256sum.txt` existe na release, formato `sha  ./nome`); **(b)** assinatura Authenticode lida pelo próprio Windows — stdlib não faz isso, então um filho de PowerShell de uma linha é a **exceção declarada e justificada**; **(c)** qualquer caminho duvidoso devolve `ok=False` (**fail-closed**: sem assinatura válida, nada roda).

As duas armadilhas abaixo foram **medidas nesta máquina** (seção 3) e o código as reflete: com `-Command` o `$args[0]` **não** binda (o caminho tem de entrar no script, aspas simples com aspas dobradas) e a saída do PowerShell **não** é garantidamente UTF-8 (`errors="replace"`).

**Files:**
- Create: `src/thero/artifactcheck.py`
- Test: `tests/test_artifactcheck.py`

- [ ] **Step 1: Escrever os testes que falham**

`tests/test_artifactcheck.py`:

```python
"""Integridade de artefato: nenhum teste baixa nada nem abre PowerShell."""

import hashlib
import os
import subprocess

import pytest

from thero import artifactcheck

GOOD = "4a6514323eb8c131f6c8bb651b4fe2edf5f1525f4fd8b84315ba20f1af3e210f"
SUMS = (
    "25f64b810b947145095956533e1bdf56eacea2673c55a7e586be4515fc882c9f  "
    "./install.sh\n"
    "535193f38f3344e5b08f5d1c171c31ce11aa17f0124ff69ae26d8ec7fe06fa62  "
    "./ollama-windows-amd64.zip\n"
    "%s  ./OllamaSetup.exe\n" % GOOD
)


class Done:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout, self.stderr, self.returncode = stdout, stderr, returncode


def test_parse_checksums_reads_the_published_line():
    assert artifactcheck.parse_checksums(SUMS, "OllamaSetup.exe") == GOOD


@pytest.mark.parametrize("prefix", ["*", "./", ".\\", "*./"])
def test_parse_checksums_accepts_the_binary_marker(prefix):
    line = "%s  %sOllamaSetup.exe" % (GOOD, prefix)
    assert artifactcheck.parse_checksums(line, "OllamaSetup.exe") == GOOD


def test_parse_checksums_raises_listing_what_it_saw():
    with pytest.raises(LookupError) as info:
        artifactcheck.parse_checksums(SUMS, "other.exe")
    text = str(info.value)
    assert "other.exe" in text and "OllamaSetup.exe" in text


def test_parse_checksums_refuses_a_wrong_length_digest():
    with pytest.raises(LookupError):
        artifactcheck.parse_checksums(SUMS.replace(GOOD, "abcd"),
                                      "OllamaSetup.exe")


def test_sha256_of_matches_hashlib(tmp_path):
    target = tmp_path / "blob"
    target.write_bytes(b"ollama" * 10)
    assert artifactcheck.sha256_of(target) == hashlib.sha256(
        b"ollama" * 10).hexdigest()


def test_read_latest_tag_accepts_the_official_shape():
    assert artifactcheck.read_latest_tag(
        '{"tag_name": "v0.34.4"}') == "v0.34.4"


@pytest.mark.parametrize("payload", ["", "null", "[]", '{"tag_name": 7}',
                                     '{"tag_name": "../x"}', "not json"])
def test_read_latest_tag_refuses_garbage(payload):
    with pytest.raises(ValueError):
        artifactcheck.read_latest_tag(payload)


def test_ps_quote_doubles_the_single_quote():
    assert artifactcheck.ps_quote(r"C:\x\a'b.exe") == "'C:\\x\\a''b.exe'"


def test_sign_script_carries_the_path_not_an_argument():
    # Medido na maquina: com `-Command`, $args[0] NAO recebe o caminho.
    script = artifactcheck.sign_script(r"C:\temp\a'b.exe")
    assert "$args" not in script
    assert "'C:\\temp\\a''b.exe'" in script


def test_sign_command_is_a_closed_argv():
    command = artifactcheck.sign_command(r"C:\temp\x.exe")
    assert command[:4] == ["powershell", "-NoProfile", "-NonInteractive",
                           "-Command"]
    assert len(command) == 5


def test_signature_reads_status_and_subject():
    seen = {}

    def runner(command, **kwargs):
        seen["argv"] = command
        seen.update(kwargs)
        return Done("Valid|CN=Ollama, O=Ollama, C=US\n")

    out = artifactcheck.signature(r"C:\t\OllamaSetup.exe", runner=runner)
    assert out["ok"] is True
    assert (out["status"], out["subject"]) == (
        "Valid", "CN=Ollama, O=Ollama, C=US")
    assert seen["timeout"] == artifactcheck.SIGN_TIMEOUT
    assert seen["errors"] == "replace"   # stdout PS nao e UTF-8 garantido
    assert seen["shell"] is False
    assert seen["env"] is None           # nada herdado/alterado as pressas


def test_signature_of_an_unsigned_file_is_not_ok():
    out = artifactcheck.signature(
        r"C:\t\nope.exe", runner=lambda *a, **k: Done("NotSigned|\n"))
    assert out["ok"] is False and out["status"] == "NotSigned"


def test_signature_without_a_child_is_not_ok():
    def boom(command, **kwargs):
        raise OSError("powershell ausente")

    out = artifactcheck.signature(r"C:\t\x.exe", runner=boom)
    assert out["ok"] is False and "powershell" in out["error"]


def test_the_signature_child_never_flashes_a_console():
    seen = {}

    def runner(command, **kwargs):
        seen.update(kwargs)
        return Done("Valid|CN=Ollama")

    artifactcheck.signature(r"C:\t\x.exe", runner=runner)
    if os.name == "nt":
        assert seen["creationflags"] == subprocess.CREATE_NO_WINDOW
    else:
        assert "creationflags" not in seen


def test_verdict_refuses_a_digest_mismatch(tmp_path):
    target = tmp_path / "setup.exe"
    target.write_bytes(b"qualquer coisa")
    out = artifactcheck.verdict(target, sha256_published="0" * 64,
                                signature_ok=True, signer="CN=Ollama")
    assert out["ok"] is False and "sha256" in out["reason"]


def test_verdict_refuses_an_untrusted_publisher(tmp_path):
    target = tmp_path / "setup.exe"
    target.write_bytes(b"x")
    out = artifactcheck.verdict(target, sha256_published="",
                                signature_ok=True, signer="CN=Alguem")
    assert out["ok"] is False and "assinante" in out["reason"]


def test_verdict_refuses_a_non_valid_signature(tmp_path):
    target = tmp_path / "setup.exe"
    target.write_bytes(b"x")
    out = artifactcheck.verdict(target, sha256_published="",
                                signature_ok=False, signer="")
    assert out["ok"] is False and "assinatura" in out["reason"]


def test_verdict_accepts_the_measured_pair(tmp_path):
    target = tmp_path / "setup.exe"
    target.write_bytes(b"x")
    digest = artifactcheck.sha256_of(target)
    out = artifactcheck.verdict(target, sha256_published=digest,
                                signature_ok=True,
                                signer="CN=Ollama, O=Ollama, C=US")
    assert out["ok"] is True and out["reason"] == ""


def test_check_wires_the_two_locks(tmp_path, monkeypatch):
    target = tmp_path / "setup.exe"
    target.write_bytes(b"x")
    digest = artifactcheck.sha256_of(target)
    monkeypatch.setattr(
        artifactcheck, "signature",
        lambda path, runner=None: {"ok": True, "status": "Valid",
                                   "subject": "CN=Ollama", "error": ""})
    out = artifactcheck.check(target, expected_sha256=digest)
    assert out["ok"] is True and out["sha256"] == digest


def test_check_refuses_the_wrong_bytes(tmp_path):
    (tmp_path / "setup.exe").write_bytes(b"x")
    out = artifactcheck.check(tmp_path / "setup.exe",
                              expected_sha256=GOOD,
                              runner=lambda *a, **k: Done("Valid|CN=Ollama"))
    assert out["ok"] is False and "sha256" in out["reason"]
```

- [ ] **Step 2: Rodar para ver falhar**

Run: `python -m pytest tests/test_artifactcheck.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'thero.artifactcheck'`

- [ ] **Step 3: Escrever o módulo**

`src/thero/artifactcheck.py`:

```python
"""Integridade do artefato que vamos executar: saber o que rodou na maquina.

Politica (e escolha de projeto, escrita aqui para nao ser 'melhorada' por
acidente):
1. o SHA-256 e SEMPRE medido; quando a release publica um digest
   (`sha256sum.txt`, confirmado na Task 2) ele e OBRIGATORIO e uma divergencia
   mata o fluxo;
2. a assinatura Authenticode do arquivo e a segunda trava, lida pelo proprio
   Windows. stdlib nao verifica Authenticode, entao um filho de PowerShell de
   uma linha e a unica excecao stdlib deste plano -- declarada aqui;
3. fail-closed: sem as duas, nada roda e o motivo volta por escrito.

Duas armadilhas desta maquina, medidas na secao 3 do plano e refletidas no
codigo: com `-Command` um argumento extra NAO binda em `$args[0]` (o caminho
entra dentro do script, aspas simples com aspas dobradas) e a saida do
PowerShell nao e UTF-8 garantido (`errors="replace"`).

Proibido print(): modulo do processo da ponte. O runner e sempre injetavel.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Callable, Optional

from thero import enginedata

CHUNK = 262144
SIGN_TIMEOUT = 60
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_SCRIPT = ("$s = Get-AuthenticodeSignature -LiteralPath {path}; "
           "$s.Status.ToString() + '|' + $s.SignerCertificate.Subject")


def sha256_of(path) -> str:
    digest = hashlib.sha256()
    with open(str(path), "rb") as handle:
        while True:
            block = handle.read(CHUNK)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def parse_checksums(text: str, name: str) -> str:
    """Procura `name` numa lista no formato publicado `sha  ./nome`.

    Ausencia NAO e "sem checksum": e LookupError listando o que ele viu, para
    o executor descobrir que o nome do artefato mudou.
    """
    seen = []
    for line in (text or "").splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) != 2:
            continue
        digest, path = parts[0].lower(), parts[1].strip()
        base = path.replace("\\", "/")
        if base.startswith("*"):
            base = base[1:]
        base = base.rsplit("/", 1)[-1]
        seen.append(base)
        if base.casefold() == name.casefold() and _HEX64.match(digest):
            return digest
    raise LookupError("sem digest publicado para %r (vi: %s)"
                      % (name, ", ".join(seen[:8]) or "nada"))


def read_latest_tag(payload: object) -> str:
    """`tag_name` do JSON da API de release, validado antes de virar URL."""
    if not isinstance(payload, str):
        raise ValueError("a resposta da release precisa ser texto")
    try:
        data = json.loads(payload)
    except ValueError:
        raise ValueError("a resposta da release nao e JSON")
    if not isinstance(data, dict):
        raise ValueError("a resposta da release nao e um objeto")
    tag = data.get("tag_name")
    if not enginedata.is_release_tag(tag):
        raise ValueError("tag de release inesperada: %r" % (tag,))
    return tag


def ps_quote(value: object) -> str:
    """Aspas simples de PowerShell: o unico escape e dobrar a aspa."""
    return "'" + str(value).replace("'", "''") + "'"


def sign_script(path) -> str:
    target = Path(str(path))
    if not _NAME.match(target.name or ""):
        raise ValueError("nome de artefato inesperado: %r" % (target.name,))
    return _SCRIPT.format(path=ps_quote(path))


def sign_command(path) -> list:
    """argv fechado: sem shell, sem argumento solto, caminho no script."""
    return ["powershell", "-NoProfile", "-NonInteractive", "-Command",
            sign_script(path)]


def signature(path, *, runner: Optional[Callable] = None) -> dict:
    """Le a assinatura de um arquivo com o Windows, sem confiar em nada.

    `env` explicito como None: herdamos o ambiente do processo, nao montamos
    um falso retrato do ambiente do usuario.
    """
    out = {"ok": False, "status": "", "subject": "", "error": ""}
    kwargs = {"capture_output": True, "text": True, "encoding": "utf-8",
              "errors": "replace", "timeout": SIGN_TIMEOUT, "shell": False,
              "env": None}
    if os.name == "nt":
        # Sem isto, uma janela de console pisca na tela do usuario a cada
        # checagem (regra ja aprendida no host ps2exe sem console do Thero).
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        completed = (runner or subprocess.run)(sign_command(path), **kwargs)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        # ValueError vem de sign_script: nome inesperado nunca vira processo.
        out["error"] = "nao consegui verificar a assinatura: %s" % exc
        return out
    text = (completed.stdout or "").strip()
    if getattr(completed, "returncode", 0) or not text:
        out["error"] = "o powershell nao respondeu (rc %s)" % getattr(
            completed, "returncode", "?")
        return out
    status, _, subject = text.partition("|")
    out["status"] = status.strip()
    out["subject"] = subject.strip()
    out["ok"] = out["status"] == "Valid" and bool(out["subject"])
    return out


def verdict(path, *, sha256_published: str, signature_ok: bool,
            signer: str) -> dict:
    """A regra reunida, separada da rede e do processo para poder testar.

    `sha256_published` vazio = a fonte nao publica digest para este artefato
    (a Task 2 decide se esse cenario existe): ai o digest medido vai por
    escrito para o usuario e para o relatorio, e a assinatura vira a trava.
    """
    measured = sha256_of(path)
    published = (sha256_published or "").strip().lower()
    reason = ""
    if published and measured != published:
        reason = ("o sha256 do arquivo nao bate com o publicado na release "
                  "(medido %s, publicado %s)" % (measured, published))
    elif not signature_ok:
        reason = "a assinatura Authenticode nao e valida neste artefato"
    elif enginedata.EXPECTED_PUBLISHER.lower() not in (signer or "").lower():
        reason = ("o assinante nao e o esperado (%s; visto: %s)"
                  % (enginedata.EXPECTED_PUBLISHER, signer or "nada"))
    return {"ok": not reason, "reason": reason, "sha256": measured,
            "publisher": signer, "published": published}


def check(path, *, expected_sha256: str = "",
          runner: Optional[Callable] = None) -> dict:
    """As duas travas, na ordem que nao abre PowerShell antes do file."""
    target = Path(str(path))
    try:
        signed = signature(target, runner=runner)
    except ValueError as exc:
        return {"ok": False, "reason": str(exc), "sha256": "",
                "publisher": "", "published": ""}
    try:
        out = verdict(target, sha256_published=expected_sha256,
                      signature_ok=signed["ok"], signer=signed["subject"])
    except OSError as exc:
        return {"ok": False, "reason": "nao consegui abrir %s: %s"
                % (target.name, exc), "sha256": "", "publisher": "",
                "published": ""}
    if out["ok"] and signed["error"]:
        out["ok"] = False
        out["reason"] = signed["error"]
    return out
```

- [ ] **Step 4: Rodar para ver passar**

Run: `python -m pytest tests/test_artifactcheck.py -q`
Expected: `28 passed` (18 funções de caso único + 4 casos do marcador binário + 6 casos de JSON lixo)

Run: `python -m pytest tests/ -q`
Expected: `B + 41` passed

- [ ] **Step 5: Commit local**

```bash
git add src/thero/artifactcheck.py tests/test_artifactcheck.py
git commit -m "feat(artifactcheck): sha256 publicado e assinatura authenticode como travas"
```

**Acumulado: B + 41.**

---

### Task 8: `download.py` — bytes que só viram arquivo depois de bater

Requisito do dono: instalação interrompida no meio tem de ser recuperável. A implementação é banal e é por isso que funciona: escrever `<nome>.part`, conferir, `os.replace()`. Um arquivo **final** nunca existe pela metade, e recomeçar é só chamar de novo.

**Files:**
- Create: `src/thero/download.py`
- Test: `tests/test_download.py`

- [ ] **Step 1: Escrever os testes que falham**

`tests/test_download.py`:

```python
"""Download sem rede: o opener e injetado e nada sai daqui para a internet."""

import hashlib

import pytest

from thero import download

BODY = b"instalador"
GOOD = hashlib.sha256(BODY).hexdigest()


class FakeResponse:
    def __init__(self, chunks):
        self._chunks = list(chunks)

    def read(self, size=-1):
        if not self._chunks:
            return b""
        if size and 0 < size < len(self._chunks[0]):
            head = self._chunks[0][:size]
            self._chunks[0] = self._chunks[0][size:]
            return head
        return self._chunks.pop(0)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeUrlopen:
    """Assina (request, timeout=) como o urlopen real: e a unica forma do
    teste provar que o timeout nunca chega como None nem como posicional."""

    def __init__(self, chunks, error=None):
        self._chunks = list(chunks)
        self._error = error
        self.requests = []

    def __call__(self, request, timeout=None):
        self.requests.append((request, timeout))
        if self._error:
            raise self._error
        return FakeResponse(self._chunks)


def get(url="https://x/OllamaSetup.exe", name="OllamaSetup.exe",
        tmp_path=None, **kwargs):
    """Atalho dos testes: o workdir e o `tmp_path` do fixture, sempre.

    O `opener` e sempre injetado aqui (nunca monkeypatch de rede implicita):
    e o padrao do repo, e e o que garante que a suite rode sem internet.
    """
    fake = kwargs.pop("opener", None) or FakeUrlopen([BODY])
    out = download.to_file(url, name, tmp_path, opener=fake, **kwargs)
    return out, fake


def test_it_writes_the_file_and_reports_the_digest(tmp_path):
    out, _ = get(tmp_path=tmp_path, expected_sha256=GOOD)
    assert out["ok"] is True and out["sha256"] == GOOD and out["bytes"] == 10
    assert (tmp_path / "OllamaSetup.exe").read_bytes() == BODY


def test_no_part_file_survives_a_success(tmp_path):
    get(tmp_path=tmp_path, expected_sha256=GOOD)
    assert [p.name for p in tmp_path.iterdir()] == ["OllamaSetup.exe"]


def test_a_digest_mismatch_refuses_the_file(tmp_path):
    out, _ = get(tmp_path=tmp_path, expected_sha256="0" * 64)
    assert out["ok"] is False and "sha256" in out["reason"]
    assert not (tmp_path / "OllamaSetup.exe").exists()


def test_a_failed_body_leaves_only_the_part(tmp_path):
    fake = FakeUrlopen([b"ins"], error=OSError("conexao cortada"))
    out = download.to_file("https://x/y", "OllamaSetup.exe", tmp_path,
                           expected_sha256=GOOD, opener=fake)
    assert out["ok"] is False and "conexao" in out["reason"]
    assert not (tmp_path / "OllamaSetup.exe").exists()
    assert list(tmp_path.glob("*.part")) == []   # falhou antes de abrir o file


def test_a_cut_mid_stream_leaves_the_part_for_the_next_run(tmp_path):
    # O caso que o dono citou: "instalacao interrompida no meio". O `.part`
    # fica (nao e apagado por nos) e o arquivo FINAL nunca aparece.
    class Cutter(FakeUrlopen):
        def __call__(self, request, timeout=None):
            response = FakeResponse([b"instalador"])
            original = response.read

            def read(size=-1):
                chunk = original(size)
                if not original.__dict__.get("armed"):
                    original.__dict__["armed"] = True
                    return chunk
                raise OSError("corpo cortado no meio")

            response.read = read
            return response

    out = download.to_file("https://x/y", "OllamaSetup.exe", tmp_path,
                           expected_sha256=GOOD, opener=Cutter([b"ignored"]))
    assert out["ok"] is False
    assert (tmp_path / "OllamaSetup.exe.part").read_bytes() == b"instalador"
    assert not (tmp_path / "OllamaSetup.exe").exists()


def test_progress_sees_bytes_as_they_arrive(tmp_path):
    seen = []
    download.to_file("https://x/y", "OllamaSetup.exe", tmp_path,
                     opener=FakeUrlopen([b"insta", b"lador"]),
                     total_bytes=10,
                     progress=lambda done, total: seen.append((done, total)))
    assert seen == [(5, 10), (10, 10)]


def test_the_ceiling_stops_a_runaway_response(tmp_path):
    out = download.to_file("https://x/y", "OllamaSetup.exe", tmp_path,
                           opener=FakeUrlopen([b"x" * 64] * 10),
                           max_bytes=100)
    assert out["ok"] is False and "teto" in out["reason"]


def test_http_is_refused_before_anything_opens(tmp_path):
    fake = FakeUrlopen([BODY])
    out = download.to_file("http://x/y", "OllamaSetup.exe", tmp_path,
                           opener=fake)
    assert out["ok"] is False and not fake.requests


def test_the_url_never_echoes_a_userinfo_credential(tmp_path):
    out = download.to_file("https://sk-secret@x/y", "OllamaSetup.exe",
                           tmp_path, expected_sha256="0" * 64)
    assert out["ok"] is False and "sk-secret" not in out["reason"]


@pytest.mark.parametrize("name", ["", "../setup.exe", "a b.exe",
                                  "setup.exe;calc", "x" * 200])
def test_only_a_boring_file_name_gets_through(name, tmp_path):
    out, fake = get("https://x/y", name, tmp_path)
    assert out["ok"] is False and "nome" in out["reason"]
    assert not fake.requests


def test_a_complete_good_file_is_not_downloaded_again(tmp_path):
    (tmp_path / "OllamaSetup.exe").write_bytes(BODY)
    fake = FakeUrlopen([BODY])
    out = download.to_file("https://x/y", "OllamaSetup.exe", tmp_path,
                           expected_sha256=GOOD, opener=fake)
    assert out["ok"] is True and out["skipped"] is True and not fake.requests


def test_an_existing_wrong_file_is_redownloaded(tmp_path):
    (tmp_path / "OllamaSetup.exe").write_bytes(b"outra coisa")
    out, fake = get(tmp_path=tmp_path, expected_sha256=GOOD)
    assert out["ok"] is True and out["skipped"] is False and fake.requests


def test_nothing_is_written_outside_the_workdir(tmp_path):
    work = tmp_path / "work"
    other = tmp_path / "outra"
    other.mkdir()
    download.to_file("https://x/y", "OllamaSetup.exe", work,
                     expected_sha256=GOOD, opener=FakeUrlopen([BODY]))
    assert list(other.iterdir()) == []
    assert [p.name for p in work.iterdir()] == ["OllamaSetup.exe"]


def test_the_timeout_is_always_a_keyword_and_never_none(tmp_path):
    _, fake = get(tmp_path=tmp_path, expected_sha256=GOOD)
    assert fake.requests[0][1] == download.READ_TIMEOUT


def test_the_request_is_an_object_never_a_bare_string(tmp_path):
    _, fake = get(tmp_path=tmp_path, expected_sha256=GOOD)
    assert hasattr(fake.requests[0][0], "full_url")
```

- [ ] **Step 2: Rodar para ver falhar**

Run: `python -m pytest tests/test_download.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'thero.download'`

- [ ] **Step 3: Escrever o módulo**

`src/thero/download.py`:

```python
"""Um arquivo baixado da internet com as tres coisas que importam.

1. so https, e nenhum texto devolvido ecoa o userinfo da URL (a base de um
   endpoint pode carregar chave colada no campo errado -- mesmo vetor que ja
   custou `providers.redact`);
2. o arquivo final so aparece quando o digest bate: `.part` + `os.replace()`
   e a unika forma de uma conexao cortada no meio deixar a maquina
   recomecavel, que e o requisito de "instalacao interrompida no meio";
3. nada escreve fora do workdir informado, e o workdir nunca e o payload do
   Thero (espinha dorsal: nenhum binario de terceiro mora dentro de nos).

Rede injetavel por parametro (`opener`), no mesmo padrao de
`localmodels.urlopen`. Proibido print(): modulo do processo da ponte.
"""

from __future__ import annotations

import hashlib
import os
import re
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from thero import providers

urlopen = urllib.request.urlopen   # costura de teste, modulo-a-fora

CHUNK = 262144
READ_TIMEOUT = 60.0
MAX_BYTES = 8 * 1024 ** 3
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_PART = ".part"


def _report(reason: str = "", **fields) -> dict:
    out = {"ok": not reason, "path": "", "bytes": 0, "sha256": "",
           "skipped": False, "reason": reason}
    out.update(fields)
    return out


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with open(str(path), "rb") as handle:
        while True:
            block = handle.read(CHUNK)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def to_file(url: str, name: str, workdir, *, expected_sha256: str = "",
            total_bytes: int = 0, progress: Optional[Callable] = None,
            opener: Optional[Callable] = None,
            max_bytes: int = MAX_BYTES) -> dict:
    """Baixa `url` para `workdir/name`, conferindo `expected_sha256`.

    `expected_sha256` vazio = nenhum digest publicado foi confirmado pela
    Task 2; nesse caso este modulo devolve o bytes e o digest medidos e a
    decisao de executar passa por `artifactcheck.check` (assinatura), nunca
    por aqui.
    """
    if not _NAME.match(name or ""):
        return _report("nome de arquivo nao aceito (letras, digitos, "
                       "'.', '_', '-'): %r" % (name,))
    target = Path(str(workdir))
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return _report("nao consegui criar o workdir: %s" % exc)
    final = target / name
    part = target / (name + _PART)
    published = (expected_sha256 or "").strip().lower()

    if final.exists():
        try:
            existing = _digest(final)
        except OSError as exc:
            return _report("nao consegui ler %s: %s" % (name, exc))
        if not published or existing == published:
            return {"ok": True, "path": str(final),
                    "bytes": final.stat().st_size, "sha256": existing,
                    "skipped": True, "reason": ""}

    if not str(url).lower().startswith("https://"):
        return _report("apenas https baixa artefato de instalacao: %s"
                       % providers.redact(url))
    ceiling = int(max_bytes)

    request = urllib.request.Request(str(url), method="GET")
    opened = opener or urlopen
    written = 0
    try:
        with opened(request, timeout=READ_TIMEOUT) as response:
            with open(str(part), "wb") as sink:
                while True:
                    block = response.read(CHUNK)
                    if not block:
                        break
                    written += len(block)
                    if written > ceiling:
                        raise OSError("o corpo passou o teto de %d bytes"
                                      % ceiling)
                    sink.write(block)
                    sink.flush()
                    if progress is not None:
                        progress(written, int(total_bytes or ceiling))
    except OSError as exc:
        # OSError cobre URLError/HTTPError/socket/ValueError-de-teto: em
        # qualquer um deles o `.part` fica la, integro ate onde deu, e a
        # proxima chamada recomeca do zero sem publicar nada pela metade.
        return _report("a conexao falhou em %s: %s"
                       % (providers.redact(url), exc), bytes=written)

    if total_bytes and written != int(total_bytes):
        return _report("vieram %d bytes, esperavamos %d (corpo cortado)"
                       % (written, int(total_bytes)), bytes=written)
    try:
        measured = _digest(part)
    except OSError as exc:
        return _report("nao consegui reler a descarga: %s" % exc)
    if published and measured != published:
        return _report("o sha256 da descarga nao bate com o publicado "
                       "(medido %s, publicado %s)" % (measured, published),
                       sha256=measured)
    try:
        os.replace(str(part), str(final))
    except OSError as exc:
        return _report("nao consegui publicar o arquivo final: %s" % exc)
    return {"ok": True, "path": str(final), "bytes": final.stat().st_size,
            "sha256": measured, "skipped": False, "reason": ""}
```

Decisões escritas para o executor não improvisar:

- **`os.replace` é a única "remoção" deste módulo** (ela consome o `.part`). Não há `os.remove`/`os.unlink`/`shutil.rmtree` aqui, e a Task 13 prova isso por AST. Um `.part` órfão é lixo inofensivo na pasta de trabalho e **não** é apagado por nós.
- `providers.redact(url)` é a única fonte de redação (o docstring de `providers.redact` diz explicitamente que existe para não copiar a regex para outro módulo).
- `total_bytes` vem da Task 1 (`Content-Length` medido), não do ambiente nem de uma suposição.

- [ ] **Step 4: Rodar para ver passar**

Run: `python -m pytest tests/test_download.py -q`
Expected: `19 passed` (14 funções de caso único + 5 casos de nome rejeitado)

Run: `python -m pytest tests/ -q`
Expected: `B + 60` passed

- [ ] **Step 5: Commit local**

```bash
git add src/thero/download.py tests/test_download.py
git commit -m "feat(download): https, teto de bytes e .part publicado so depois do digest"
```

**Acumulado: B + 60.**

---

## Fase C — O que não é Ollama (Task 9)

### Task 9: Amarrar o provedor local não-Ollama (JÁ IMPLEMENTADO — não reescrever)

**Isto mudou durante a escrita deste plano.** O commit `0287c92` (`feat(providers): LM Studio registravel sem a sonda do Ollama, veto de host intacto`) já entregou o requisito, com desenho **diferente** do que este plano prescrevia (`localep.py` + `providers._ollama_family`): o classificador shipped é `localmodels.has_endpoint_path(base)` e o veto de host solto é `localmodels.guard_host(base)`. **Não criar `localep.py`, não adicionar `_ollama_family`, não mexer em `presets.py`.** Duplicar aqui seria deixar duas fontes da mesma regra — exatamente o que o docstring de `providers.redact` proíbe.

O que **é** desta task: travar por teste o contrato que o onboarding do motor (Tasks 10-13) passa a consumir, porque hoje só existem os 6 testes do próprio commit e eles não amarram a fronteira de segurança que nos interessa.

Regras que continuam duras e que os testes abaixo provam:

- `_assert_loopback` **não** foi afrouxado: virou dois vetos (`_assert_loopback_host` + `_assert_no_path`) e `guard_base` continua sendo os dois em série. Provar isso é o teste 5.
- O LM Studio **não** vira Ollama: sem sonda, sem `/api/tags`, sem adivinhar `/v1/models`.
- Conhecido e aceito: `guard_host` tolera userinfo num host de loopback (`http://chave@127.0.0.1:1234/v1`), porque nada aqui conecta nessa base e a mensagem não ecoa o texto. Não acrescentar leitura/escrita de credencial a esse ramo: se um dia formos *usar* o endpoint, a chave sai de um nome de variável, como em `providers.register`.
- O contrato `ATHENA_OLLAMA_HOST`/`SENTINEL_OLLAMA_HOST` é **do Ollama**: um provedor com caminho não pode virar esse valor (teste 8 — e é por isso que `engineinstall.consumer_env_targets`, Task 11, recusa escrever config sem provedor Ollama na config).

**Files:**
- Create: `tests/test_providers_local_non_ollama.py`
- Modify: nada em `src/`

- [ ] **Step 1: Ler o que já existe antes de escrever qualquer coisa**

Run: `git show 0287c92 --stat`
Run: `python -c "from thero import localmodels; print(localmodels.has_endpoint_path('http://127.0.0.1:1234/v1'), localmodels.guard_host('http://127.0.0.1:1234/v1'))"`
Expected: `True http://127.0.0.1:1234/v1`

Run: `python -c "from thero import localmodels; print(localmodels.guard_base('http://127.0.0.1:1234/v1'))"`
Expected: `ValueError: a base do Ollama nao aceita caminho: ...` — se isto **não** levantar, o veto foi afrouxado: pare e reporte.

- [ ] **Step 2: Escrever o teste que trava o contrato**

`tests/test_providers_local_non_ollama.py`:

```python
"""O ramo nao-Ollama que ja existe na arvore, travado por teste.

Nada aqui reimplementa: `0287c92` entregou `has_endpoint_path`/`guard_host` e
o ramo "sem sonda" de `providers.register`. Estes testes amarram as tres
coisas que o onboarding do motor (Tasks 10-13) passa a depender, e que um
refactor futuro poderia esquecer.
"""

import pytest

from thero import apply, localmodels, providers


class Boom:
    def __init__(self):
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError("nenhuma rede era para acontecer aqui")


LMSTUDIO = {"id": "lmstudio", "label": "LM Studio (local)", "kind": "local",
            "authKind": "local", "base": "http://127.0.0.1:1234/v1",
            "transport": "OpenAI-compativel local"}
OLLAMA = {"id": "ollama", "label": "Ollama (local)", "kind": "local",
          "authKind": "local", "base": "http://127.0.0.1:11434",
          "transport": "API nativa Ollama", "preset": "ollama"}


def test_lmstudio_registers_without_the_ollama_probe(monkeypatch):
    def explode(base):
        raise AssertionError("a sonda do Ollama nao roda em base com caminho")

    monkeypatch.setattr(providers.localmodels, "list_models", explode)
    monkeypatch.setattr(localmodels, "urlopen", Boom())
    out = providers.register(LMSTUDIO)
    assert out["ok"] is True and out["authState"] == "sem sonda"
    assert "sabemos que ele existe" in out["msg"]
    assert "nao sabemos listar" in out["msg"]


def test_the_honest_message_does_not_echo_a_credential(monkeypatch):
    monkeypatch.setattr(localmodels, "urlopen", Boom())
    sneaky = dict(LMSTUDIO, base="http://sk-segredo@127.0.0.1:1234/v1")
    out = providers.register(sneaky)
    assert out["ok"] is True and "sk-segredo" not in out["msg"]


def test_a_remote_local_base_is_still_blocked(monkeypatch):
    fake = Boom()
    monkeypatch.setattr(localmodels, "urlopen", fake)
    out = providers.register(dict(LMSTUDIO,
                                  base="http://host.exemplo.com:1234/v1"))
    assert out["ok"] is False and out["authState"] == "bloqueado"
    assert "loopback" in out["msg"] and fake.calls == 0


def test_the_ollama_family_still_probes(monkeypatch):
    seen = {}

    def fake_list(base):
        seen["base"] = base
        return {"ok": True, "models": [{"name": "llama3.2"}], "error": ""}

    monkeypatch.setattr(providers.localmodels, "list_models", fake_list)
    out = providers.register(OLLAMA)
    assert out["ok"] is True
    assert seen["base"] == "http://127.0.0.1:11434"


def test_the_ollama_client_still_refuses_a_path():
    # A fronteira de seguranca nao afrouxou: o que mudou foi o veto de HOST
    # para provedores que nao sao a API do Ollama.
    with pytest.raises(ValueError):
        localmodels.guard_base("http://127.0.0.1:11434/v1")


def test_guard_host_accepts_a_loopback_path_and_nothing_else():
    assert localmodels.guard_host("http://localhost:1234/v1") == (
        "http://localhost:1234/v1")
    with pytest.raises(ValueError):
        localmodels.guard_host("http://10.0.0.5:1234/v1")


def test_has_endpoint_path_is_a_pure_url_question(monkeypatch):
    fake = Boom()
    monkeypatch.setattr(localmodels, "urlopen", fake)
    assert localmodels.has_endpoint_path("http://127.0.0.1:1234/v1")
    assert not localmodels.has_endpoint_path("http://127.0.0.1:11434")
    assert localmodels.has_endpoint_path("http://127.0.0.1:11434?x=1")
    assert fake.calls == 0   # nenhum pedido: e so urlparse


def test_a_non_ollama_provider_never_becomes_the_consumers_host():
    # ATHENA_/SENTINEL_OLLAMA_HOST sao contratos DO Ollama.
    # `apply._ollama_base` casa preset/id == "ollama"; sem ele, devolve o
    # padrao 11434 -- nunca o /v1 do LM Studio. E por isso que
    # `consumer_env_targets` (Task 11) recusa
    # escrever a $PROFILE sem provedor Ollama na config.
    cfg = {"providers": [LMSTUDIO]}
    assert apply._ollama_base(cfg) == "http://127.0.0.1:11434"
    assert localmodels.has_endpoint_path(LMSTUDIO["base"])
```

- [ ] **Step 3: Rodar**

Run: `python -m pytest tests/test_providers_local_non_ollama.py tests/test_providers.py tests/test_localmodels.py -q`
Expected: `99 passed` (8 novos + 59 de `tests/test_providers.py` + 32 de `tests/test_localmodels.py`, números medidos hoje nesta árvore; conte **delta de 8**, se os antigos tiverem mudado. Se algum teste antigo falhar, você tocou em `src/` e deve reverter)

Run: `python -m pytest tests/ -q`
Expected: `B + 68` passed

- [ ] **Step 4: Provar que `src/` não foi tocado nesta task**

Run: `git status --short src/`
Expected: saída **vazia**.

- [ ] **Step 5: Commit local**

```bash
git add tests/test_providers_local_non_ollama.py
git commit -m "test(providers): amarra o ramo local sem sonda que a arvore ja entrega"
```

**Acumulado: B + 68.**

---

## Fase D — O provisionamento (Tasks 10-13)

### Task 10: `engineinstall.py` — retrato e plano (detectar, avisar, pedir o clique)

Aqui vive a decisão: o que falta, o que vai acontecer, quanto pesa, e o que **nós não vamos fazer**. Nenhuma rede e nenhum subprocesso dentro de `probe()`/`plan()` além da sonda HTTP já existente (`localmodels.status`), sempre injetável.

**Files:**
- Create: `src/thero/engineinstall.py`
- Test: `tests/test_engineinstall_plan.py`

- [ ] **Step 1: Escrever os testes que falham**

`tests/test_engineinstall_plan.py`:

```python
"""Retrato e plano do motor: deteccao, tamanho, consentimento, idempotencia."""

import pytest

from thero import engineinstall, enginedata


def which(found):
    return lambda name: r"C:\x\%s.exe" % name if found else None


def portrait(binary=False, up=False, models=(), error=""):
    return {"binaryFound": binary, "up": up, "models": list(models),
            "base": "http://127.0.0.1:11434",
            "binary": r"C:\x\ollama.exe" if binary else "", "error": error}


def status_fn(payload):
    return lambda base="": payload


def test_probe_reads_the_binary_and_the_http_port_only():
    seen = []

    def status(base=""):
        seen.append(base)
        return {"up": True, "base": base, "models": [{"name": "llama3.2"}],
                "error": ""}

    out = engineinstall.probe(which=which(True), status_fn=status)
    assert out["binaryFound"] is True and out["up"] is True
    assert out["models"] == ["llama3.2"]
    # O probe passa a base VAZIA e deixa o cliente resolver o default: uma
    # unika fonte para o padrao loopback (`localmodels.normalize_base`).
    assert seen == [""]
    assert out["base"] == "http://127.0.0.1:11434"


def test_probe_reports_an_absent_engine_without_inventing_a_process():
    out = engineinstall.probe(which=which(False), status_fn=status_fn(
        {"up": False, "base": "http://127.0.0.1:11434", "models": [],
         "error": "conexao recusada"}))
    assert out["binaryFound"] is False and out["up"] is False
    assert "recusada" in out["error"]


def test_probe_refuses_a_remote_base_before_any_network():
    with pytest.raises(ValueError):
        engineinstall.probe(base="http://ollama.exemplo:11434",
                            which=which(False), status_fn=status_fn({}))


def test_the_engine_environment_is_never_read(monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "http://10.0.0.9:11434")
    monkeypatch.setenv("OLLAMA_MODELS", r"D:\outra\pasta")
    seen = []
    engineinstall.probe(which=which(False),
                        status_fn=lambda base="": seen.append(base) or {
                            "up": False, "base": "", "models": [],
                            "error": ""})
    assert seen == [""]


def test_has_model_matches_a_bare_name_to_its_tag():
    models = ["llama3.2:latest", "qwen3-coder-next:q4_K_M"]
    assert engineinstall.has_model(models, "llama3.2")
    assert engineinstall.has_model(models, "qwen3-coder-next")
    assert engineinstall.has_model(models, "qwen3-coder-next:q4_K_M")
    assert not engineinstall.has_model(models, "qwen3-coder-next:q8_0")
    assert not engineinstall.has_model(models, "")


def test_plan_of_an_absent_engine_offers_the_installer_and_the_models():
    out = engineinstall.plan(portrait=portrait(),
                             free_bytes=400 * enginedata.GIB)
    assert out["state"] == "engine-absent"
    assert out["actions"] == ["installer", "models", "env"]
    assert out["missingModels"] == list(enginedata.CONSUMER_DEFAULTS)
    assert out["requiresConsent"] is True
    assert out["enoughSpace"] is True


def test_the_consent_carries_the_measured_sizes():
    out = engineinstall.plan(portrait=portrait(),
                             free_bytes=400 * enginedata.GIB)
    assert out["modelSizeGb"]["qwen3-coder-next"] == 52.0
    text = out["consentText"]
    for name in enginedata.CONSUMER_DEFAULTS:
        assert name in text
    assert "52" in text and "GB" in text
    assert out["sizeHuman"]


def test_the_installer_size_comes_from_the_measured_artifact():
    out = engineinstall.plan(portrait=portrait(),
                             free_bytes=400 * enginedata.GIB)
    assert out["installerBytes"] == enginedata.KNOWN_GOOD_BYTES


def test_a_present_engine_is_never_reinstalled_and_stops_to_ask():
    out = engineinstall.plan(
        portrait=portrait(binary=True, up=False,
                          error="conexao recusada"),
        free_bytes=400 * enginedata.GIB)
    assert out["state"] == "engine-idle"
    assert "installer" not in out["actions"]
    assert "O Thero nao vai instalar por cima" in out["stopAndAsk"]


def test_a_running_engine_with_the_models_is_a_no_op():
    out = engineinstall.plan(
        portrait=portrait(binary=True, up=True,
                          models=["llama3.2:latest",
                                  "qwen3-coder-next:q4_K_M"]),
        free_bytes=100 * enginedata.GIB)
    assert out["state"] == "ready" and out["actions"] == []
    assert out["requiresConsent"] is False and out["consentText"] == ""


def test_not_enough_disk_stops_before_any_consent():
    out = engineinstall.plan(portrait=portrait(), free_bytes=2 *
                             enginedata.GIB)
    assert out["enoughSpace"] is False and out["actions"] == []
    assert "insuficiente" in out["msg"]


def test_a_model_without_a_measured_size_is_asked_not_promised():
    out = engineinstall.plan(portrait=portrait(binary=True, up=True),
                             want=("modelo-deschecido",),
                             free_bytes=100 * enginedata.GIB)
    assert out["modelSizeGb"] == {}
    assert out["unknownSizes"] == ["modelo-deschecido"]
    assert "tamanho desconhecido" in out["msg"]
    assert "models" in out["actions"]
    assert "desconhecido" in out["consentText"]


def test_blobs_on_disk_are_revealed_not_redownloaded():
    # Estado REAL desta maquina (secao 3): modelos na pasta padrao, motor
    # ausente. Instalar o motor revela o que ja existe; baixar de novo seria
    # desperdiciar 52 GB do usuario.
    out = engineinstall.plan(portrait=portrait(),
                             want=("llama3.2", "qwen3-coder-next"),
                             free_bytes=400 * enginedata.GIB,
                             on_disk={"llama3.2": True})
    assert out["missingModels"] == ["qwen3-coder-next"]
    assert "revelar" in out["msg"] or "ja estao na maquina" in out["msg"]


def test_the_plan_text_never_promises_to_start_the_engine():
    out = engineinstall.plan(portrait=portrait(),
                             free_bytes=400 * enginedata.GIB)
    joined = " ".join(str(v) for v in out.values() if isinstance(v, str))
    for banned in ("ollama serve", "inicamos o", "subimos o", "reiniciamos"):
        assert banned not in joined
    assert "Nao vamos: iniciar" in out["willNotDo"]
    assert out["actions"] and set(out["actions"]) <= {"installer", "models",
                                                      "env"}


def test_every_plan_string_crosses_the_bridge_as_ascii():
    out = engineinstall.plan(portrait=portrait(),
                             free_bytes=400 * enginedata.GIB)
    for key in ("willDo", "willNotDo", "consentText", "msg", "stopAndAsk",
                "sizeHuman"):
        assert out[key].isascii(), key
```

- [ ] **Step 2: Rodar para ver falhar**

Run: `python -m pytest tests/test_engineinstall_plan.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'thero.engineinstall'`

- [ ] **Step 3: Escrever o módulo (parte 1 — retrato e plano)**

`src/thero/engineinstall.py`:

```python
"""Provisionamento do motor local: instalar como o usuario faria, e sair.

A frase que manda neste modulo: O Thero NUNCA inicia, para, reinicia nem
mantem o Ollama -- apenas observa a porta por HTTP, com paciencia. O ciclo de
vida e do Ollama (start-up dele, portas dele, atualizacao dele); o nosso
programa pode estar fechado e a IA continua la, igual a uma maquina onde o
usuario instalou na mao e passou os dados de acesso.

Os unicos processos que este modulo gera sao (a) o instalador oficial da
release, que abre, faz o trabalho dele e MORRE, e (b) a linha de PowerShell
que le a assinatura desse arquivo (em `artifactcheck`). Nada de servico, nada
de registro de start-up, nada de porta, nada de pasta de modelo. `
assert_not_lifecycle()` e a trava que corre antes de qualquer spawn.

Depois de instalado, o acesso e o de sempre: HTTP em loopback
(`thero.localmodels`) + `ATHENA_OLLAMA_HOST`/`MODEL` e
`SENTINEL_OLLAMA_HOST`/`MODEL` na `$PROFILE` (`thero.apply`).

Regras de canal: proibido print() (o stdout e o JSON da ponte); nenhum valor
de variavel de ambiente lido (o host vem do provedor salvo em config.json,
provado por teste); rede e subprocesso sempre injetaveis; todo texto que sai
daqui e ASCII sem acento.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Callable, Iterator, Optional

from thero import apply, artifactcheck, download, enginedata, localmodels
from thero import providers
from thero.settings import ENV_MARKER_END, ENV_MARKER_START

urlopen = urllib.request.urlopen   # costura de teste, padrao do repo

ACTIONS = ("installer", "models", "env")
STATE_LABELS = ("engine-absent", "engine-idle", "models-missing", "ready")

WILL_DO = (
    "Vamos: baixar o instalador oficial do Ollama por https para uma pasta "
    "de trabalho no seu temp, conferir a assinatura e o sha256 publicados, "
    "abrir o assistente de instalacao dele (que roda, instala e fecha), "
    "esperar o motor responder em loopback, baixar os modelos que faltam "
    "pela API local e escrever o bloco de ambiente na sua $PROFILE."
)
WILL_NOT_DO = (
    "Nao vamos: iniciar, parar, reiniciar ou matar o processo do Ollama; "
    "criar servico do Windows; escrever chave de start-up no registro; "
    "escolher ou mudar porta; alterar a pasta onde ele grava os modelos; "
    "instalar por cima de um Ollama que ja exista; nem apagar o que voce ja "
    "baixou. Se o motor nao subir sozinho, abrir o Ollama e tarefa sua."
)
IDLE_MSG = (
    "O motor ja esta instalado, mas nao esta respondendo em {base}. O Thero "
    "nao vai instalar por cima nem iniciar o Ollama: o ciclo de vida e dele. "
    "Abra o Ollama (menu Iniciar ou bandeja) e recomece; nada foi alterado."
)
SPACE_MSG = (
    "Espaco em disco insuficiente para o download (livre {freeGb} GB, "
    "necessario {needGb} GB). Libere espaco ou escolha um modelo menor: o "
    "Thero nao apaga nada em seu nome."
)
ENGINE_NOT_UP_MSG = (
    "O Ollama nao respondeu em {base} depois de {waited:.0f}s. O Thero nao "
    "inicia o motor: abra o Ollama pelo menu Iniciar e rode de novo."
)
NOT_FOUND_MSG = "O Ollama nao esta instalado nesta maquina."
START_HINT = (
    "Se ele nao subir sozinho ao logar, inicie-o pelo menu Iniciar: a "
    "decisao de start-up e da instalacao do Ollama, nao do Thero."
)

INSTALLER_TIMEOUT = 1800.0
ENGINE_UP_DEADLINE = 180.0
ENGINE_UP_INTERVAL = 2.0
RELEASE_TIMEOUT = 20.0

_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_PERCENT = re.compile(r"([0-9]{1,3})\s*%")


# --------------------------------------------------------------------------
# Trava de posse: o ciclo de vida do motor nao e nosso.
# --------------------------------------------------------------------------
class OwnershipError(Exception):
    """Alguem tentou usar este modulo para gerir o processo do Ollama."""


LIFECYCLE_WORDS = frozenset({"serve", "start", "stop", "kill", "restart",
                             "shutdown", "uninstall"})
LIFECYCLE_PHRASES = ("reg add", "reg delete", "schtasks", "sc create",
                     "sc delete", "net start", "net stop")


def assert_not_lifecycle(command: object) -> list:
    """Levanta OwnershipError ANTES de virar processo. Devolve a original.

    Comparacao por TOKEN (cada item do argv dividido em espacos), nao por
    substring: um caminho contendo "start" (ex.: `C:\\Start Menu\\...`) e so
    um caminho, mas um argv colado em string (`"C:\\x\\ollama.exe serve"`) e o
    vetor classico do CreateProcess, que reinterpreta a linha de comando.
    As frases (`reg add`, `schtasks`, `net start`) sao procuradas no conjunto
    porque uma chave de registro nao e um argv nosso.
    """
    if isinstance(command, str):
        raise OwnershipError("comando como string nao e aceito (shell=False)")
    original = list(command)
    if not original:
        raise OwnershipError("comando vazio")
    tokens = []
    for part in original:
        text = str(part).strip().lower()
        tokens.extend(text.split())
    for token in tokens:
        if token in LIFECYCLE_WORDS:
            raise OwnershipError(
                "o Thero nao gere o ciclo de vida do motor: %s" % token)
    joined = " ".join(tokens)
    for phrase in LIFECYCLE_PHRASES:
        if phrase in joined:
            raise OwnershipError(
                "o Thero nao mexe em servico nem em registro: %s" % phrase)
    return original


# --------------------------------------------------------------------------
# Retrato (leitura) e plano (decisao).
# --------------------------------------------------------------------------
def probe(*, base: str = "", which: Optional[Callable] = None,
          status_fn: Optional[Callable] = None) -> dict:
    """(esta no PATH?, responde em loopback?) sem tocar em nada.

    `base` vem do provedor salvo em `config.json`, nunca de `OLLAMA_HOST`:
    variavel de ambiente do motor nao e canal de configuracao do Thero, e uma
    base remota morre no veto de loopback do `localmodels` antes de qualquer
    requisicao.
    """
    finder = which or shutil.which
    status = status_fn or localmodels.status
    url_base = localmodels.guard_base(base) if base else ""
    # `status("")` resolve o default loopback dentro do proprio
    # `normalize_base`: a unica fonte do padrao continua sendo o cliente.
    info = status(url_base)
    models = [str(entry.get("name", "")) for entry in (info.get("models")
                                                       or [])
              if isinstance(entry, dict)]
    found = finder("ollama") or ""
    return {
        "binaryFound": bool(found),
        "binary": str(found),
        "up": bool(info.get("up")),
        "base": str(info.get("base") or url_base or _default_base()),
        "models": models,
        "error": str(info.get("error") or ""),
    }


def _default_base() -> str:
    return localmodels.normalize_base("")


def has_model(models, name: object) -> bool:
    """`llama3.2` casa com `llama3.2:latest`; com tag explicita, so exatamente.

    O `list_models` do Ollama devolve sempre a forma taggada, e o default dos
    consumidores (`athena/settings.py`, `sentinel/settings.py`) e o nome
    curto: sem esta regra o plano pediria para baixar o que ja esta la.
    """
    wanted = str(name or "").strip()
    if not wanted:
        return False
    listed = [str(item or "") for item in (models or [])]
    if wanted in listed:
        return True
    if ":" in wanted:
        return False
    prefix = wanted + ":"
    return any(item == wanted or item.startswith(prefix) for item in listed)


def _sizes(missing, installer: bool) -> dict:
    """Tamanho anunciado por modelo, com o peso do instalador junto.

    O que nao esta na tabela medida (Task 5) nao ganha numero de cabeca: vai
    para `unknownSizes`, o consentimento diz "tamanho desconhecido" e o
    download so acontece com um SIM explicito daquele item.
    """
    sizes, unknown = {}, []
    for name in missing:
        value = enginedata.MODEL_SIZE_GIB.get(name)
        if value:
            sizes[name] = float(value)
        else:
            unknown.append(name)
    gigabytes = sum(sizes.values())
    if installer:
        gigabytes += enginedata.KNOWN_GOOD_BYTES / float(enginedata.GIB)
    return {"modelSizeGb": sizes, "unknownSizes": unknown,
            "installerBytes": enginedata.KNOWN_GOOD_BYTES if installer
            else 0,
            "needGb": round(gigabytes, 1),
            "sizeHuman": "%.1f GB" % gigabytes}


def plan(*, portrait: Optional[dict] = None, want=None,
         free_bytes: int = 0, on_disk: Optional[dict] = None) -> dict:
    """O que falta, o que vai acontecer, quanto pesa, o que NAO faremos.

    Idempotencia vem de RE-OBSERVAR a maquina, nao de arquivo nosso: rodar
    duas vezes numa maquina ja no estado de instalacao manual devolve
    `actions == []` e consentimento vazio.
    """
    seen = dict(portrait or {})
    wanted = [str(n) for n in (want or enginedata.CONSUMER_DEFAULTS)]
    installed = [str(m) for m in (seen.get("models") or [])]
    disk = {}
    for key, value in (on_disk or {}).items():
        disk[str(key)] = bool(value)
    absent = [n for n in wanted if not has_model(installed, n)]
    # Blob na pasta padrao do Ollama com o motor fora do ar: a instalacao
    # REVELA o que ja existe, nao rebaixa. So vale quando nao ha como
    # perguntar ao motor (com ele de pe, quem decide e o `/api/tags`).
    revealed = [n for n in absent if disk.get(n)] if not seen.get("up") else []
    missing = [n for n in absent if n not in revealed]
    base = str(seen.get("base") or _default_base())
    engine_present = bool(seen.get("binaryFound") or seen.get("up"))

    estimate = _sizes(missing, installer=not engine_present)
    try:
        free = int(free_bytes)
    except (TypeError, ValueError):
        free = 0
    free_gb = round(free / float(enginedata.GIB), 1)
    enough = free >= int((estimate["needGb"] + enginedata.DISK_RESERVE_GIB)
                         * enginedata.GIB)

    actions, msg = [], ""
    if not engine_present:
        state = "engine-absent"
        if not enough:
            msg = SPACE_MSG.format(freeGb=free_gb, needGb=estimate["needGb"])
        else:
            actions = ["installer", "env"]
            if missing:
                actions.insert(1, "models")
    elif not seen.get("up"):
        state = "engine-idle"
        msg = IDLE_MSG.format(base=base)
    elif missing:
        state = "models-missing"
        actions = ["models", "env"]
    else:
        state = "ready"

    if revealed:
        msg = (msg + " " if msg else "") + (
            "Estes modelos ja estao na maquina e vao ser revelados pela "
            "instalacao do motor, nao baixados de novo: %s."
            % ", ".join(revealed))
    if estimate["unknownSizes"] and "models" in actions:
        msg = (msg + " " if msg else "") + (
            "Sem tamanho medido para %s (tamanho desconhecido): o download "
            "deles so acontece com um SIM explicito."
            % ", ".join(estimate["unknownSizes"]))

    stop_and_ask = ""
    if engine_present:
        stop_and_ask = ("O motor ja existe nesta maquina: o Thero nao vai "
                        "instalar por cima nem tocar no processo dele")
        stop_and_ask += ("; vamos apenas baixar o que falta. Confirma?"
                         if actions else ". Nada sera instalado.")

    consent_lines = []
    if actions:
        consent_lines.append(WILL_DO)
        consent_lines.append(WILL_NOT_DO)
        if "installer" in actions:
            consent_lines.append(
                "Instalador oficial: %.1f GB, baixado de %s."
                % (enginedata.KNOWN_GOOD_BYTES / float(enginedata.GIB),
                   enginedata.INSTALLER_URL))
        for name in missing:
            if name in estimate["modelSizeGb"]:
                consent_lines.append("Modelo %s: %.1f GB (tabela da Task 5)."
                                     % (name, estimate["modelSizeGb"][name]))
            else:
                consent_lines.append("Modelo %s: tamanho desconhecido." % name)
        consent_lines.append(
            "Espaco livre: %.1f GB; necessario: %.1f GB (com folga de %.0f "
            "GB)." % (free_gb, estimate["needGb"],
                      enginedata.DISK_RESERVE_GIB))
        if stop_and_ask:
            consent_lines.append(stop_and_ask)

    out = {
        "ok": True,
        "state": state,
        "actions": actions,
        "enginePresent": engine_present,
        "engineRunning": bool(seen.get("up")),
        "binaryFound": bool(seen.get("binaryFound")),
        "base": base,
        "host": base,
        "presentModels": installed,
        "missingModels": missing,
        "revealedModels": revealed,
        "modelSizeGb": estimate["modelSizeGb"],
        "unknownSizes": estimate["unknownSizes"],
        "installerBytes": estimate["installerBytes"],
        "sizeHuman": estimate["sizeHuman"],
        "needGb": estimate["needGb"],
        "freeGb": free_gb,
        "enoughSpace": enough,
        "requiresConsent": bool(actions),
        "stopAndAsk": stop_and_ask,
        "consentText": "\n".join(consent_lines),
        "willDo": WILL_DO,
        "willNotDo": WILL_NOT_DO,
        "msg": msg,
    }
    if out["state"] not in STATE_LABELS:
        raise RuntimeError("estado fora do contrato: %s" % out["state"])
    for action in out["actions"]:
        if action not in ACTIONS:
            raise RuntimeError("acao fora do contrato: %s" % action)
    return out
```

- [ ] **Step 4: Rodar para ver passar**

Run: `python -m pytest tests/test_engineinstall_plan.py -q`
Expected: `15 passed`

Run: `python -m pytest tests/ -q`
Expected: `B + 83` passed

- [ ] **Step 5: Commit local**

```bash
git add src/thero/engineinstall.py tests/test_engineinstall_plan.py
git commit -m "feat(engineinstall): retrato e plano com tamanho, consentimento e idempotencia"
```

**Acumulado: B + 83.**

---

### Task 11: `engineinstall.py` — os passos isolados (abrir, esperar, baixar modelo, escrever config)

Cada passo é uma função pequena, injetável e testável sozinha. A composição (`execute`) vem na Task 12, depois de as peças estarem presas por teste.

**Files:**
- Modify: `src/thero/engineinstall.py` (acrescentar `import tempfile` ao bloco de imports; acrescentar as funções no fim do arquivo)
- Test: `tests/test_engineinstall_steps.py`

- [ ] **Step 1: Escrever os testes que falham**

`tests/test_engineinstall_steps.py`:

```python
"""Cada passo do fluxo, com o efeito colateral injetado.

Regra do repo: o runner e a funcao de rede sao PASSADOS (ou monkeypatchados na
costura publica do modulo) -- nenhum teste abre socket nem gera processo.
"""

import json

import pytest

from thero import engineinstall, enginedata


class Pages:
    def __init__(self, mapping):
        self.mapping = mapping
        self.urls = []

    def __call__(self, request, timeout=None):
        self.urls.append((getattr(request, "full_url", str(request)), timeout))
        body = self.mapping[getattr(request, "full_url", str(request))]

        class Response:
            def read(self):
                return body.encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        return Response()


def release_pages(tag="v0.34.4"):
    return {
        enginedata.RELEASE_API_URL: json.dumps({"tag_name": tag}),
        enginedata.checksums_url(tag): "%s  ./%s\n" % (
            enginedata.KNOWN_GOOD_SHA256, enginedata.INSTALLER_NAME),
    }


def test_release_info_reads_the_tag_and_the_published_digest(monkeypatch):
    pages = Pages(release_pages())
    monkeypatch.setattr(engineinstall, "urlopen", pages)
    out = engineinstall.release_info()
    assert out["ok"] is True and out["tag"] == "v0.34.4"
    assert out["sha256"] == enginedata.KNOWN_GOOD_SHA256
    assert pages.urls[0][1] == engineinstall.RELEASE_TIMEOUT


def test_an_untrusted_tag_never_becomes_a_url(monkeypatch):
    pages = Pages({enginedata.RELEASE_API_URL: '{"tag_name": "../x"}'})
    monkeypatch.setattr(engineinstall, "urlopen", pages)
    out = engineinstall.release_info()
    assert out["ok"] is False and len(pages.urls) == 1
    assert out["tag"] == "" and out["sha256"] == ""


def test_launch_installer_runs_only_the_artifact():
    seen = []

    def runner(command):
        seen.append(command)
        return type("R", (), {"returncode": 0})()

    out = engineinstall.launch_installer(r"C:\t\OllamaSetup.exe",
                                        runner=runner)
    assert seen == [[r"C:\t\OllamaSetup.exe"] + list(
        enginedata.INSTALLER_ARGS)]
    assert out["ok"] is True and out["returncode"] == 0


def test_launch_installer_reports_a_failing_assistant():
    out = engineinstall.launch_installer(
        r"C:\t\x.exe", runner=lambda command: type("R", (),
                                                   {"returncode": 6})())
    assert out["ok"] is False and "instalador" in out["error"].lower()


def test_launch_installer_refuses_a_lifecycle_command():
    with pytest.raises(engineinstall.OwnershipError):
        engineinstall.launch_installer(r"C:\t\ollama.exe serve")


def test_nothing_we_generate_looks_like_engine_ownership():
    for command in (["ollama", "serve"], ["taskkill", "/IM", "ollama.exe"],
                    ["net", "start", "OllamaService"], ["sc", "create", "X"],
                    ["reg", "add", "HKCU"], ["ollama", "stop"]):
        with pytest.raises(engineinstall.OwnershipError):
            engineinstall.assert_not_lifecycle(command)
    # Um caminho contendo "start" NAO e um comando de start-up: a comparacao
    # e por item inteiro do argv, nao por substring.
    engineinstall.assert_not_lifecycle([r"C:\Start Menu\OllamaSetup.exe"])


def test_percent_from_line_reads_the_ollama_status():
    assert engineinstall.percent_from_line("pulling manifest") == -1
    assert engineinstall.percent_from_line("transferring 42 %") == 42
    assert engineinstall.percent_from_line("100%") == 100
    assert engineinstall.percent_from_line("999 %") == -1


def test_wait_returns_when_the_port_answers():
    out = engineinstall.wait_for_engine(
        base="http://127.0.0.1:11434",
        probe_fn=lambda base="": {"up": True, "base": base,
                                  "models": ["llama3.2:latest"],
                                  "binaryFound": True, "binary": "",
                                  "error": ""})
    assert out["ok"] is True and out["models"] == ["llama3.2:latest"]
    assert out["tries"] == 1


def test_wait_gives_up_and_tells_the_user_to_open_it_himself():
    naps = []
    out = engineinstall.wait_for_engine(
        base="http://127.0.0.1:11434",
        probe_fn=lambda base="": {"up": False, "base": base, "models": [],
                                  "binaryFound": True, "binary": "",
                                  "error": "recusada"},
        sleep=naps.append, deadline=6, interval=2)
    assert out["ok"] is False and len(naps) == 3
    assert "abra o Ollama" in out["msg"]
    assert "iniciamos" not in out["msg"]


def test_wait_uses_the_injected_sleeper_and_never_a_real_sleep():
    calls = []
    engineinstall.wait_for_engine(
        probe_fn=lambda base="": {"up": False, "base": "", "models": [],
                                  "binaryFound": False, "binary": "",
                                  "error": ""},
        sleep=calls.append, deadline=1, interval=1)
    assert calls == [1]


def test_ensure_model_pulls_through_the_api_not_a_process():
    seen = {}

    def emit(name, base=""):
        seen["name"], seen["base"] = name, base
        return iter([("out", "pulling manifest"), ("out", "50 %"),
                     ("out", "verifying sha256 digest"), ("exit", 0)])

    progress = []
    out = engineinstall.ensure_model("llama3.2",
                                     base="http://127.0.0.1:11434",
                                     progress=lambda *a: progress.append(a),
                                     emit=emit)
    assert seen["name"] == "llama3.2"
    assert out["ok"] is True and out["code"] == 0 and out["lines"] == 3
    assert progress == [("llama3.2", "pulling manifest", -1),
                        ("llama3.2", "50 %", 50),
                        ("llama3.2", "verifying sha256 digest", -1)]


def test_ensure_model_refuses_an_empty_name():
    # `localmodels.pull("")` devolve exit 2; silenciar isso entregaria um nome
    # vazio ao escritor da $PROFILE, que gravaria `..._MODEL = ""`.
    with pytest.raises(ValueError):
        engineinstall.ensure_model("", emit=lambda name, base="": iter([]))


def test_a_broken_pull_is_a_failure_with_a_reason():
    out = engineinstall.ensure_model(
        "llama3.2", emit=lambda name, base="": iter(
            [("out", "error: no space left"), ("exit", 1)]))
    assert out["ok"] is False and "no space left" in out["error"]


def test_stream_model_keeps_the_bridge_contract():
    got = list(engineinstall.stream_model(
        "llama3.2", emit=lambda name, base="": iter([("out", "50 %"),
                                                     ("exit", 0)])))
    assert got == [("out", "50 %"), ("exit", 0)]
    assert list(engineinstall.stream_model(" "))[-1] == ("exit", 2)


def test_consumer_env_targets_refuses_a_config_without_an_ollama_provider():
    cfg = {"providers": [{"id": "lmstudio", "preset": "lmstudio",
                          "base": "http://127.0.0.1:1234/v1"}]}
    out = engineinstall.consumer_env_targets(cfg)
    assert out["ok"] is False and "Ollama" in out["msg"]


def test_consumer_env_targets_refuses_a_remote_ollama_without_echoing_it():
    cfg = {"providers": [{"id": "ollama", "preset": "ollama",
                          "base": "http://sk-segredo@host.exemplo:11434"}]}
    out = engineinstall.consumer_env_targets(cfg)
    assert out["ok"] is False and "sk-segredo" not in out["msg"]


def test_write_env_refuses_a_down_engine(monkeypatch):
    calls = []
    monkeypatch.setattr(engineinstall, "probe", lambda **k: {
        "up": False, "base": "http://127.0.0.1:11434", "models": [],
        "binaryFound": True, "binary": "", "error": "recusada"})
    out = engineinstall.write_consumer_env({"providers": []},
                                          apply_fn=lambda *a: calls.append(a))
    assert out["ok"] is False and not calls and "$PROFILE" in out["msg"]


def test_write_env_refuses_a_missing_model_before_writing_the_name():
    calls = []
    out = engineinstall.write_consumer_env(
        {"providers": [{"id": "ollama", "preset": "ollama",
                        "base": "http://127.0.0.1:11434"}],
         "routing": {"athena": "llama3.2", "sentinel": "qwen3-coder-next"}},
        seen={"up": True, "base": "http://127.0.0.1:11434",
              "models": ["llama3.2:latest"], "binaryFound": True,
              "binary": "", "error": ""},
        apply_fn=lambda *a: calls.append(a))
    assert out["ok"] is False and not calls
    assert out["missing"] == ["qwen3-coder-next"]


def test_write_env_delegates_to_apply_and_carries_the_answer():
    seen = {}

    def apply_fn(cfg, profile):
        seen["profile"] = str(profile)
        return {"ok": True, "written": str(profile), "backup": "b.ps1",
                "msg": "ambiente Athena/Sentinel atualizado na $PROFILE"}

    out = engineinstall.write_consumer_env(
        {"providers": [{"id": "ollama", "preset": "ollama",
                        "base": "http://127.0.0.1:11434"}],
         "routing": {"athena": "llama3.2"}},
        profile=r"C:\p\Microsoft.PowerShell_profile.ps1",
        seen={"up": True, "base": "http://127.0.0.1:11434",
              "models": ["llama3.2:latest"], "binaryFound": True,
              "binary": "", "error": ""},
        apply_fn=apply_fn)
    assert out["ok"] is True and out["backup"] == "b.ps1"
    assert seen["profile"].endswith("Microsoft.PowerShell_profile.ps1")


def test_write_env_stops_when_the_config_has_no_ollama_provider():
    calls = []
    out = engineinstall.write_consumer_env(
        {"providers": [], "routing": {}},
        seen={"up": True, "base": "", "models": [], "binaryFound": True,
              "binary": "", "error": ""},
        apply_fn=lambda *a: calls.append(a))
    assert out["ok"] is False and not calls


def test_resolve_profile_uses_the_injected_resolver():
    assert engineinstall.resolve_profile(
        resolver=lambda: r"C:\p\profile.ps1") == r"C:\p\profile.ps1"
    assert engineinstall.resolve_profile(resolver=lambda: None) is None
```

- [ ] **Step 2: Rodar para ver falhar**

Run: `python -m pytest tests/test_engineinstall_steps.py -q`
Expected: FAIL — `AttributeError: module 'thero.engineinstall' has no attribute 'release_info'`

- [ ] **Step 3: Acrescentar os passos ao módulo**

No bloco de imports de `src/thero/engineinstall.py`, acrescentar `import tempfile`. Depois, **no fim do arquivo**:

```python
# --------------------------------------------------------------------------
# Passos. Cada um e uma funcao pequena com a fronteira injetavel: e assim que
# os testes rodam offline, e assim que o executor nao consegue "melhorar" um
# passo virando dono do processo do motor.
# --------------------------------------------------------------------------
def _get_text(url, *, opener=None, timeout=RELEASE_TIMEOUT) -> str:
    request = urllib.request.Request(str(url), method="GET")
    with (opener or urlopen)(request, timeout=timeout) as response:
        return response.read().decode("utf-8", "replace")


def release_info(*, opener=None) -> dict:
    """Tag corrente + digest publicado do NOSSO artefato.

    A ordem importa e nao e enfeite: a tag vem da API, o digest vem da lista
    daquela tag, e a descarga usa a porta de entrada fixa do `enginedata`. O
    URL assinado que a pagina de download mostra NUNCA e usado: ele expira em
    minutos (medido na Task 1), e uma URL que expira entre o consentimento e
    o clique nao pode ser o que nos executamos.
    """
    out = {"ok": False, "tag": "", "sha256": "", "error": ""}
    try:
        tag = artifactcheck.read_latest_tag(
            _get_text(enginedata.RELEASE_API_URL, opener=opener))
        listing = _get_text(enginedata.checksums_url(tag), opener=opener)
        digest = artifactcheck.parse_checksums(listing,
                                               enginedata.INSTALLER_NAME)
    except (OSError, ValueError, LookupError) as exc:
        out["error"] = "nao consegui a informacao da release: %s" % exc
        return out
    out.update(ok=True, tag=tag, sha256=digest)
    return out


def _run_installer(command):
    """`shell=False` com timeout, SEM capturar saida e SEM CREATE_NO_WINDOW: o
    assistente precisa de janela para o usuario clicar, e ele morre no fim. A
    guarda de posse roda aqui, dentro do proprio comando."""
    return subprocess.run(assert_not_lifecycle(command), shell=False,
                          timeout=INSTALLER_TIMEOUT)


def launch_installer(path, *, runner=None) -> dict:
    """Abre o instalador oficial: ele roda, instala e MORRE.

    Isto nao e o motor e nao deixa nada de pe. Quem sobe depois e o Ollama,
    por conta propria (a Task 4 registra se ele se inscreveu no start-up; o
    Thero nao inscreve).
    """
    command = assert_not_lifecycle(
        [str(path)] + list(enginedata.INSTALLER_ARGS))
    report = {"ok": False, "returncode": None, "command": command, "error": ""}
    try:
        done = (runner or _run_installer)(command)
    except (OSError, subprocess.SubprocessError) as exc:
        report["error"] = "nao consegui abrir o instalador: %s" % exc
        return report
    code = getattr(done, "returncode", None)
    report["returncode"] = code
    if code in (0, None):
        report["ok"] = True
    else:
        report["error"] = ("o instalador devolveu %s; rode-o de novo pelo "
                           "menu Iniciar ou instale na mao" % code)
    return report


def percent_from_line(text) -> int:
    """Percentual quando a linha do Ollama traz um, senao -1 (desconhecido).

    Le a mesma linha que o `localmodels.pull` ja repassa: nao mudamos o
    contrato da geradora (isso e decisao da ponte, Task 7 la) e a tela nao
    inventa progresso.
    """
    match = _PERCENT.search(str(text or ""))
    if match is None:
        return -1
    value = int(match.group(1))
    return value if 0 <= value <= 100 else -1


def _pct(done, total) -> int:
    try:
        value = int(int(done) * 100 / int(total))
    except (TypeError, ValueError, ZeroDivisionError):
        return -1
    return value if 0 <= value <= 100 else -1


def wait_for_engine(*, base: str = "", probe_fn=None, sleep=None,
                    deadline=None, interval=None) -> dict:
    """SO OLHA a porta por HTTP, com paciencia. Nao inicia, nao para, nao
    reinicia: se o motor nao esta la, a saida e um texto pedindo ao usuario
    para abri-lo. E exatamente isso que separa provisionar de possuir."""
    look = probe_fn or probe
    nap = sleep if sleep is not None else time.sleep
    limit = ENGINE_UP_DEADLINE if deadline is None else float(deadline)
    pause = ENGINE_UP_INTERVAL if interval is None else float(interval)
    waited = 0.0
    tries = 0
    seen = {}
    while True:
        seen = look(base=base) or {}
        tries += 1
        if seen.get("up"):
            return {"ok": True, "tries": tries, "waited": waited,
                    "models": [str(m) for m in (seen.get("models") or [])],
                    "base": str(seen.get("base") or base), "msg": "",
                    "hint": "", "error": ""}
        if waited >= limit:
            break
        nap(pause)
        waited += pause
    where = str(seen.get("base") or base or _default_base())
    return {"ok": False, "tries": tries, "waited": waited, "models": [],
            "base": where, "error": str(seen.get("error") or ""),
            "msg": ENGINE_NOT_UP_MSG.format(base=where, waited=waited),
            "hint": START_HINT}


def ensure_model(name, *, base: str = "", progress=None, emit=None) -> dict:
    """Baixa um modelo pela API do motor (o processo e dele, o pedido e nosso).

    Nome vazio morre AQUI: `localmodels.pull("")` devolve `exit 2`, e se isso
    fosse silenciado o `write_consumer_env` gravaria `$env:..._MODEL = ""` --
    o defeito que o dono mandou tratar com instalacao, nao com fe.
    """
    wanted = str(name or "").strip()
    if not wanted:
        raise ValueError("informe o nome do modelo a baixar")
    stream = (emit or localmodels.pull)(wanted, base=base or _default_base())
    report = {"ok": False, "name": wanted, "lines": 0, "code": None,
              "last": "", "error": ""}
    for kind, payload in stream:
        if kind == "exit":
            report["code"] = payload
            continue
        report["lines"] += 1
        report["last"] = str(payload)
        if progress is not None:
            progress(wanted, report["last"], percent_from_line(payload))
    report["ok"] = report["code"] == 0
    if not report["ok"]:
        report["error"] = "o download de %s parou (codigo %s): %s" % (
            wanted, report["code"], report["last"] or "sem saida do motor")
    return report


def stream_model(name, *, base: str = "", emit=None):
    """Adaptador para o painel de terminal da ponte: ('out', linha) /
    ('exit', codigo) -- o contrato que `localmodels.pull` ja promete e que a
    Task 7 da ponte pretende expor como `system.process.stream_command`.

    Vive FORA da ponte de proposito: quando ela chegar, so repassa os tuplos.
    """
    wanted = str(name or "").strip()
    if not wanted:
        yield ("out", "informe o nome do modelo")
        yield ("exit", 2)
        return
    stream = (emit or localmodels.pull)(wanted, base=base or _default_base())
    for kind, payload in stream:
        if kind == "exit":
            try:
                yield ("exit", int(payload))
            except (TypeError, ValueError):
                yield ("exit", 1)
        else:
            yield ("out", str(payload))


def consumer_env_targets(cfg) -> dict:
    """Ha um provedor da familia Ollama na config, e ele e de loopback?

    Os dois pares de variaveis sao o contrato DO Ollama
    (`athena/src/athena/settings.py:52-72`, `sentinel/src/sentinel/
    settings.py:255-283`): um LM Studio em `/v1` nao atende por ele, entao
    escrever `http://127.0.0.1:11434` sem provedor Ollama seria fingir motor.
    A regra de "quem e o provedor Ollama" e a MESMA de `apply._ollama_base`
    (preset ou id == "ollama"), para as duas fontes nunca divergirem.
    """
    listed = cfg.get("providers") if isinstance(cfg, dict) else None
    for provider in listed if isinstance(listed, list) else []:
        if not isinstance(provider, dict):
            continue
        if (provider.get("preset") != "ollama"
                and provider.get("id") != "ollama"):
            continue
        pid = str(provider.get("id") or "ollama")
        try:
            base = localmodels.guard_base(provider.get("base") or "")
        except ValueError as exc:
            # O texto do veto cita a base crua; redigir antes de devolver
            # (mesma politica de `apply.apply_profile`, que chama
            # `providers.redact`).
            return {"ok": False, "base": "", "provider": pid,
                    "msg": "modelos locais so por loopback: %s"
                           % providers.redact(exc)}
        return {"ok": True, "base": base, "provider": pid, "msg": ""}
    return {"ok": False, "base": "", "provider": "",
            "msg": "nenhum provedor Ollama na config: as variaveis "
                   "ATHENA_OLLAMA_HOST/SENTINEL_OLLAMA_HOST nao tem o que "
                   "apontar"}


def resolve_profile(*, resolver=None, timeout: int = 5):
    """Delegamos a unica fonte que sabe achar a $PROFILE (o mesmo caminho do
    `envreport._profile_path`). Falhou, e None, e o chamador explica."""
    if resolver is not None:
        found = resolver()
        return str(found) if found else None
    try:
        from thero.shell_command.windows import resolve_powershell_profile

        found = resolve_powershell_profile(timeout=timeout)
    except Exception:  # noqa: BLE001 - conforto de tela, nunca queda da GUI
        return None
    return str(found) if found else None


def _routing_models(cfg) -> list:
    routing = (cfg or {}).get("routing") if isinstance(cfg, dict) else None
    routing = routing if isinstance(routing, dict) else {}
    names = []
    for consumer in providers.CONSUMERS:
        value = str(routing.get(consumer) or "").strip()
        if value and value not in names:
            names.append(value)
    return names


def write_consumer_env(cfg, *, profile=None, want=None, seen=None,
                       apply_fn=None) -> dict:
    """A unica escrita deste plano, e ela ja existia: `apply.apply_profile`.

    Recusa antes de escrever quando falta motor, quando falta modelo ou quando
    a config nao tem provedor Ollama: `$env:ATHENA_OLLAMA_MODEL` apontando para
    um nome que nao esta no motor e o defeito que o dono mandou tratar com
    instalacao (Pergunta 2 do dono).
    """
    report = {"ok": False, "written": "", "backup": "", "msg": "",
              "missing": []}
    snapshot = seen if isinstance(seen, dict) else probe()
    if not snapshot.get("up"):
        report["msg"] = ("o motor nao esta respondendo em %s: nada foi "
                         "escrito na $PROFILE"
                         % (snapshot.get("base") or _default_base()))
        return report
    wanted = ([str(n) for n in want] if want
              else _routing_models(cfg) or list(enginedata.CONSUMER_DEFAULTS))
    names = [str(n) for n in (snapshot.get("models") or [])]
    missing = [n for n in wanted if not has_model(names, n)]
    if missing:
        report["missing"] = missing
        report["msg"] = ("nada foi escrito na $PROFILE: os modelos %s ainda "
                         "nao estao no motor" % ", ".join(missing))
        return report
    targets = consumer_env_targets(cfg)
    if not targets["ok"]:
        report["msg"] = targets["msg"]
        return report
    where = profile if profile else resolve_profile()
    if not where:
        report["msg"] = "nao localizei a $PROFILE do PowerShell nesta maquina"
        return report
    writer = apply_fn or apply.apply_profile
    out = writer(cfg, Path(str(where)))
    report["ok"] = bool(out.get("ok"))
    report["written"] = str(out.get("written") or "")
    report["backup"] = str(out.get("backup") or "")
    report["msg"] = str(out.get("msg") or "")
    return report
```

- [ ] **Step 4: Rodar para ver passar**

Run: `python -m pytest tests/test_engineinstall_steps.py -q`
Expected: `21 passed`

Run: `python -m pytest tests/ -q`
Expected: `B + 104` passed

- [ ] **Step 5: Commit local**

```bash
git add src/thero/engineinstall.py tests/test_engineinstall_steps.py
git commit -m "feat(engineinstall): passos isolados com a posse do processo travada"
```

**Acumulado: B + 104.**

---

### Task 12: `execute()` — o fluxo completo, com clique, progresso e recomeço

**Files:**
- Modify: `src/thero/engineinstall.py` (acrescentar no fim)
- Test: `tests/test_engineinstall_execute.py`

- [ ] **Step 1: Escrever os testes que falham**

`tests/test_engineinstall_execute.py`:

```python
"""O fluxo completo com TODAS as pecas injetadas.

`deps` e a mesa de pecas: em teste entra fake, em producao entra a funcao real
do modulo. Nenhum teste gera processo, abre socket ou toca na $PROFILE real.
"""

import pytest

from thero import engineinstall


def ok_plan(actions=("installer", "models", "env"), missing=("llama3.2",),
            **extra):
    plan = {"ok": True, "actions": list(actions),
            "missingModels": list(missing),
            "base": "http://127.0.0.1:11434", "installerBytes": 100,
            "modelSizeGb": {"llama3.2": 2.0}, "unknownSizes": [],
            "consentText": "x", "enoughSpace": True,
            "requiresConsent": bool(actions), "msg": "",
            "state": "engine-absent"}
    plan.update(extra)
    return plan


class Log:
    def __init__(self, results=None):
        self.calls = []
        self.results = results or {}

    def step(self, name, default):
        def call(*args, **kwargs):
            self.calls.append((name, kwargs))
            value = self.results.get(name, default)
            return dict(value)
        return call


def green_log():
    return Log({
        "release": {"ok": True, "tag": "v0.34.4", "sha256": "ab",
                    "error": ""},
        "download": {"ok": True, "path": r"C:\t\OllamaSetup.exe",
                     "sha256": "ab", "bytes": 100, "reason": ""},
        "verify": {"ok": True, "reason": "", "publisher": "CN=Ollama",
                   "sha256": "ab"},
        "launch": {"ok": True, "returncode": 0, "error": ""},
        "wait": {"ok": True, "models": ["qwen2.5-coder:14b"],
                 "base": "http://127.0.0.1:11434", "msg": "", "hint": ""},
        "pull": {"ok": True, "code": 0, "error": ""},
        "env": {"ok": True, "written": "C:\\p\\profile.ps1", "backup": "b",
                "msg": "$PROFILE atualizada", "missing": []},
    })


def deps_for(log):
    return {"release": log.step("release", {}),
            "download": log.step("download", {"ok": False}),
            "verify": log.step("verify", {"ok": False}),
            "launch": log.step("launch", {"ok": False}),
            "wait": log.step("wait", {"ok": False}),
            "pull": log.step("pull", {"ok": False}),
            "env": log.step("env", {"ok": False})}


def run(plan=None, log=None, consent=lambda p: True, progress=None,
        cfg=None, deps=None):
    log = log or green_log()
    out = engineinstall.execute(plan if plan is not None else ok_plan(),
                                consent=consent, progress=progress,
                                workdir=r"C:\t",
                                cfg=cfg or {"providers": [{"id": "ollama"}]},
                                deps=deps or deps_for(log))
    return out, log


def names(log):
    return [name for name, _ in log.calls]


def test_execute_walks_the_steps_in_order():
    out, log = run()
    assert out["ok"] is True and out["stopped"] == ""
    assert names(log) == ["release", "download", "verify", "launch", "wait",
                          "pull", "env"]
    steps = [s["step"] for s in out["steps"]]
    assert steps[0] == "consent" and steps[-1] == "env"


def test_execute_refuses_without_touching_anything():
    out, log = run(consent=lambda p: False)
    assert out["ok"] is False and out["stopped"] == "consent"
    assert log.calls == []
    assert out["steps"][-1]["step"] == "consent"
    assert "nada foi baixado" in out["msg"]


def test_execute_never_installs_over_an_existing_engine():
    plan = ok_plan(actions=["models", "env"], state="models-missing")
    out, log = run(plan=plan)
    assert names(log) == ["wait", "pull", "env"]
    assert out["ok"] is True


def test_execute_stops_when_the_verification_fails():
    log = green_log()
    log.results["verify"] = {"ok": False, "reason": "assinatura invalida",
                             "publisher": "", "sha256": "ab"}
    out, _ = run(log=log)
    assert out["ok"] is False and out["stopped"] == "verify"
    assert "assinatura invalida" in out["msg"]
    assert names(log)[-1] == "verify"


def test_execute_stops_when_the_download_is_cut():
    log = green_log()
    log.results["download"] = {"ok": False, "path": "", "sha256": "",
                               "bytes": 10, "reason": "a conexao falhou"}
    out, _ = run(log=log)
    assert out["ok"] is False and out["stopped"] == "download"
    assert names(log)[-1] == "download"


def test_execute_stops_when_the_engine_never_answers():
    log = green_log()
    log.results["wait"] = {"ok": False, "models": [],
                           "base": "http://127.0.0.1:11434",
                           "msg": "o Ollama nao respondeu",
                           "hint": "abra-o pelo menu Iniciar"}
    out, _ = run(log=log)
    assert out["ok"] is False and out["stopped"] == "engine-up"
    assert "nao respondeu" in out["msg"] and "menu Iniciar" in out["msg"]
    assert "env" not in names(log) and "pull" not in names(log)


def test_execute_pulls_only_what_the_engine_still_lacks():
    # Motor ausente no plano, mas com os blobs ja na pasta padrao dele: depois
    # de subir, o re-plan nao pode prometer um download que esta na maquina.
    log = green_log()
    log.results["wait"] = {"ok": True, "models": ["llama3.2:latest",
                                                 "qwen3-coder-next"],
                           "base": "http://127.0.0.1:11434", "msg": "",
                           "hint": ""}
    out, _ = run(log=log, plan=ok_plan(missing=("llama3.2",
                                                "qwen3-coder-next")))
    assert "pull" not in names(log) and out["ok"] is True
    assert sorted(out["models"]) == ["llama3.2:latest", "qwen3-coder-next"]


def test_execute_writes_the_env_last_and_only_then():
    out, log = run()
    assert out["written"] == "C:\\p\\profile.ps1" and out["backup"] == "b"
    assert names(log)[-1] == "env"


def test_execute_is_a_green_no_op_when_nothing_is_missing():
    out, log = run(plan=ok_plan(actions=[], missing=[], state="ready",
                                requiresConsent=False, consentText=""))
    assert out["ok"] is True and log.calls == []
    assert out["steps"] == [{"step": "ready", "detail": out["msg"],
                             "percent": 100}]
    assert "nada a fazer" in out["msg"]


def test_execute_reports_the_digest_of_what_it_ran():
    out, _ = run()
    assert out["artifact"]["tag"] == "v0.34.4"
    assert out["artifact"]["sha256"] == "ab"
    assert out["artifact"]["publisher"] == "CN=Ollama"


def test_execute_carries_progress_with_an_unknown_percent():
    seen = []
    run(progress=lambda *a: seen.append(a))
    assert seen[0][0] == "consent" and seen[-1][0] == "env"
    assert all(isinstance(percent, int) for _, _, percent in seen)
    assert any(step == "download" for step, _, _ in seen)


def test_execute_never_generates_an_engine_lifecycle_command():
    # A peca real de launch e a do modulo: se trocarem o launcher por um sem
    # guarda, este teste cai.
    def honest_launch(path, *, runner=None):
        return engineinstall.launch_installer(path, runner=lambda command: (
            engineinstall.assert_not_lifecycle(command) or
            type("R", (), {"returncode": 0})()))

    log = green_log()
    deps = deps_for(log)
    deps["launch"] = honest_launch
    out, _ = run(log=log, deps=deps)
    assert out["ok"] is True
    with pytest.raises(engineinstall.OwnershipError):
        engineinstall.launch_installer("C:\\t\\ollama.exe serve")


def test_execute_refuses_a_remote_host_before_any_effect():
    log = green_log()
    with pytest.raises(ValueError):
        run(plan=ok_plan(base="http://ollama.exemplo:11434"), log=log)
    assert log.calls == []


def test_execute_pulls_a_model_of_unknown_size_after_the_click():
    plan = ok_plan(actions=["models", "env"], missing=("modelo-novo",),
                   state="models-missing", modelSizeGb={},
                   unknownSizes=("modelo-novo",))
    out, log = run(plan=plan)
    assert "pull" in names(log) and out["ok"] is True


def test_execute_passes_the_download_keywords_the_downloader_expects():
    _, log = run()
    kwargs = dict(log.calls[1][1])
    assert kwargs["name"] == "OllamaSetup.exe"
    assert kwargs["expected_sha256"] == "ab"
    assert str(kwargs["url"]).startswith("https://")
    assert "total_bytes" in kwargs and callable(kwargs["progress"])


def test_a_second_execute_on_the_same_machine_does_nothing():
    # Idempotencia de verdade: o segundo `plan()` sobre a maquina resolvida nao
    # gera acao, e o execute correspondente nao toca em nenhuma peca.
    seen = {"up": True, "base": "http://127.0.0.1:11434",
            "binaryFound": True, "binary": "C:\\x\\ollama.exe",
            "models": ["llama3.2:latest", "qwen3-coder-next"], "error": ""}
    second = engineinstall.plan(portrait=seen, free_bytes=100 * 1024 ** 3)
    out, log = run(plan=second)
    assert out["ok"] is True and log.calls == []
```

- [ ] **Step 2: Rodar para ver falhar**

Run: `python -m pytest tests/test_engineinstall_execute.py -q`
Expected: FAIL — `AttributeError: module 'thero.engineinstall' has no attribute 'execute'`

- [ ] **Step 3: Escrever o orquestrador**

No fim de `src/thero/engineinstall.py`:

```python
# --------------------------------------------------------------------------
# Composicao. `deps` e a mesa de pecas: em producao entram as funcoes reais
# deste modulo, em teste entram fakes. Nao existe outro caminho.
# --------------------------------------------------------------------------
DEP_KEYS = ("release", "download", "verify", "launch", "wait", "pull", "env")


def _workdir() -> Path:
    """Pasta de trabalho no temp do usuario. NUNCA dentro do payload do Thero:
    a espinha dorsal nao deixa binario de terceiro morar dentro de nos."""
    return Path(tempfile.gettempdir()) / "thero-engine"


def _deps(overrides=None) -> dict:
    table = {
        "release": release_info,
        "download": lambda **kwargs: download.to_file(**kwargs),
        "verify": lambda **kwargs: artifactcheck.check(**kwargs),
        "launch": launch_installer,
        "wait": wait_for_engine,
        "pull": ensure_model,
        "env": write_consumer_env,
    }
    for key, value in (overrides or {}).items():
        if key not in DEP_KEYS:
            raise ValueError("peca desconhecida: %s" % key)
        if not callable(value):
            raise ValueError("peca precisa ser chamavel: %s" % key)
        table[key] = value
    return table


def _forward(tell):
    """Progresso do modelo vira progresso do passo `models`.

    A ponte quer (step, detail, percent); `ensure_model` da (nome, linha,
    percent). Esta e a unica costura entre os dois formatos e ela mora no
    engine, para a ponte nao precisar conhecer o protocolo do Ollama.
    """
    def on_line(name, line, percent):
        tell("models", "%s: %s" % (name, line), percent)
    return on_line


def execute(plan_out, *, consent, progress=None, workdir=None, cfg=None,
            deps=None) -> dict:
    """Roda o plano, um passo por vez, e conta o que fez.

    `consent(plan) -> bool` e chamado uma unica vez, antes de qualquer efeito
    (o clique combinado). `progress(step, detail, percent)` e o unico canal
    visivel: -1 no percent significa "nao sei", nunca "terminou". A ponte
    consome os dois; nada aqui imprime.

    O relatorio devolve o digest e a tag do que foi executado: o requisito de
    cadeia de suprimentos e saber o que rodou na maquina.
    """
    plan_in = plan_out if isinstance(plan_out, dict) else {}
    actions = [str(a) for a in (plan_in.get("actions") or [])]
    # Veto de loopback na entrada: uma base remota no plano morre aqui, antes
    # de qualquer peca ser chamada (regra 5 da secao 5, sem excecao).
    base = localmodels.guard_base(str(plan_in.get("base") or ""))
    want = [str(n) for n in (plan_in.get("missingModels") or [])]

    report = {"ok": True, "stopped": "", "steps": [], "msg": "",
              "artifact": {}, "written": "", "backup": "", "models": []}

    def tell(step, detail, percent=-1):
        entry = {"step": step, "detail": str(detail), "percent": int(percent)}
        report["steps"].append(entry)
        if progress is not None:
            progress(step, entry["detail"], entry["percent"])

    def stop(kind, reason):
        report["ok"] = False
        report["stopped"] = kind
        report["msg"] = str(reason or ("parado em %s" % kind))
        tell(kind, report["msg"])
        return report

    if not actions:
        report["msg"] = ("nada a fazer: esta maquina ja esta no estado de uma "
                         "instalacao manual completa")
        tell("ready", report["msg"], 100)
        return report
    if not bool(consent(dict(plan_in))):
        return stop("consent", "nenhuma confirmacao: nada foi baixado, "
                    "instalado nem escrito")
    tell("consent", "confirmado pelo usuario", 0)

    folder = Path(str(workdir)) if workdir else _workdir()
    d = _deps(deps)

    if "installer" in actions:
        tell("release", "procurando a release oficial e o digest publicado")
        info = d["release"]()
        if not info.get("ok"):
            return stop("release", info.get("error") or
                        "a release nao informou o digest do artefato")
        digest = str(info.get("sha256") or "")
        report["artifact"] = {"tag": str(info.get("tag") or ""),
                             "sha256": digest}
        tell("release", "release %s" % info["tag"], 100)
        art = d["download"](url=enginedata.INSTALLER_URL,
                           name=enginedata.INSTALLER_NAME,
                           workdir=folder, expected_sha256=digest,
                           total_bytes=int(plan_in.get("installerBytes") or 0),
                           progress=lambda done, total: tell(
                               "download", "%d/%d bytes" % (done, total),
                               _pct(done, total)))
        report["artifact"]["path"] = str(art.get("path") or "")
        report["artifact"]["bytes"] = int(art.get("bytes") or 0)
        if art.get("sha256"):
            report["artifact"]["sha256"] = str(art["sha256"])
        if not art.get("ok"):
            return stop("download", art.get("reason") or
                        "a descarga do instalador falhou")
        tell("download", "instalador em %s" % Path(art["path"]).name, 100)
        checked = d["verify"](path=art["path"], expected_sha256=digest)
        report["artifact"]["publisher"] = str(checked.get("publisher") or "")
        if not checked.get("ok"):
            return stop("verify", checked.get("reason") or
                        "integridade nao confirmada: nada sera executado")
        tell("verify", "assinatura e sha256 conferidos", 100)
        launched = d["launch"](art["path"])
        if not launched.get("ok"):
            return stop("launch", launched.get("error") or
                        "o assistente de instalacao nao concluiu")
        tell("installer", "assistente concluido; o processo dele ja morreu",
             100)

    tell("engine-up", "observando a porta do motor (sem toca-la)")
    up = d["wait"](base=base)
    if not up.get("ok"):
        return stop("engine-up", " ".join(
            [text for text in (up.get("msg"), up.get("hint")) if text]))
    seen = {"up": True, "base": str(up.get("base") or base),
            "binaryFound": True, "binary": "", "error": "",
            "models": [str(m) for m in (up.get("models") or [])]}
    report["models"] = list(seen["models"])
    tell("engine-up", "motor respondendo em %s" % seen["base"], 100)

    if "models" in actions:
        # Re-observar antes de baixar: a instalacao do motor pode ter revelado
        # os blobs que ja estavam na pasta padrao dele.
        fresh = plan(portrait=seen, want=tuple(want))
        for name in fresh["missingModels"]:
            tell("models", "baixando %s" % name, 0)
            pulled = d["pull"](name, base=seen["base"],
                              progress=_forward(tell))
            if not pulled.get("ok"):
                return stop("pull", pulled.get("error") or
                            "o modelo %s nao desceu" % name)
            seen["models"].append(str(name))
            tell("models", "%s disponivel no motor" % name, 100)
        if not fresh["missingModels"]:
            tell("models", "o motor revelou os modelos que ja estavam na "
                           "pasta dele", 100)

    if "env" in actions:
        written = d["env"](cfg if isinstance(cfg, dict) else {}, seen=seen)
        if not written.get("ok"):
            return stop("env", written.get("msg") or
                        "a config dos consumidores nao foi escrita")
        report["written"] = str(written.get("written") or "")
        report["backup"] = str(written.get("backup") or "")
        tell("env", written.get("msg") or "config dos consumidores escrita",
             100)

    report["msg"] = ("pronto: motor em %s, %d modelo(s), config escrita em %s"
                     % (seen["base"], len(seen["models"]),
                        report["written"] or "nada"))
    return report
```

- [ ] **Step 4: Rodar para ver passar**

Run: `python -m pytest tests/test_engineinstall_execute.py -q`
Expected: `16 passed`

Run: `python -m pytest tests/ -q`
Expected: `B + 120` passed

Assinaturas que estes testes fixam (a Task 12 não pode quebrá-las ao ajustar detalhes): `deps` aceita exatamente as chaves de `DEP_KEYS`; `download`/`verify` só com as keywords mostradas; `launch(path)` posicional; `wait(base=...)`; `pull(name, base=..., progress=...)`; `env(cfg, seen=...)`; `artifactcheck.check(path=, expected_sha256=)` da Task 7; `download.to_file(url=, name=, workdir=, expected_sha256=, total_bytes=, progress=)` da Task 8.

- [ ] **Step 5: Commit local**

```bash
git add src/thero/engineinstall.py tests/test_engineinstall_execute.py
git commit -m "feat(engineinstall): execute com consentimento, progresso e replanejamento"
```

**Acumulado: B + 120.**

---

### Task 13: Política de remoção + travas estruturais que não cabem num teste unitário

`advice()` é a resposta à pergunta "e se eu quiser tirar?": desinstalar o Ollama da máquina é **ação do dono**, e o nosso papel é informar e apontar o que é nosso. E como este plano é o primeiro que gera subprocesso a partir do motor, as invariantes de canal (sem `print()`, sem rede sem costura, sem primitiva de remoção, 100% ASCII) viram **teste de AST**, não promessa de revisão.

**Files:**
- Modify: `src/thero/engineinstall.py` (acrescentar `advice()` no fim)
- Test: `tests/test_engineinstall_invariants.py`

- [ ] **Step 1: Escrever os testes que falham**

`tests/test_engineinstall_invariants.py`:

```python
"""Invariantes de canal do plano, provadas por AST (nao por promessa).

Estes testes sao a seguranca de que a Task 14 (que alguem consuma isso na
GUI) nao herde um modulo que imprime no stdout da ponte ou que apague a
instalacao de outra pessoa.
"""

import ast
from pathlib import Path

import pytest

from thero import engineinstall

SRC = Path(__file__).resolve().parent.parent / "src" / "thero"
MODULES = ("enginedata.py", "artifactcheck.py", "download.py",
           "engineinstall.py")
# Pecas que a Task 13 conhece e perdoa por serem elas mesmas a costura.
SEAM_HELPERS = {"_run_installer"}


def _tree(name):
    return ast.parse((SRC / name).read_text(encoding="utf-8"),
                     filename=str(SRC / name))


def _functions(tree):
    return [node for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]


def _mentions(node, *names):
    return any(isinstance(child, ast.Name) and child.id in names
               or isinstance(child, ast.Attribute)
               and child.attr in names
               for child in ast.walk(node))


def test_every_new_module_is_100_percent_ascii():
    for name in MODULES:
        text = (SRC / name).read_text(encoding="utf-8")
        assert text.isascii(), name
        for line in text.splitlines():
            assert len(line) <= 79, "%s:%d" % (name, len(line))


def test_no_print_call_anywhere_in_the_new_modules():
    for name in MODULES:
        for node in ast.walk(_tree(name)):
            if isinstance(node, ast.Call):
                called = node.func
                label = getattr(called, "id", getattr(called, "attr", ""))
                assert label != "print", "%s:%d" % (name, node.lineno)


@pytest.mark.parametrize("primitive", ["remove", "unlink", "rmtree", "move",
                                       "rename"])
def test_no_removal_primitive_in_the_new_modules(primitive):
    # `os.replace` e permitido: e a publicacao atomica do nosso proprio
    # `.part`, dentro do workdir que nos criamos. Apagar o que nao nos
    # pertence (blob do Ollama, instalador ja executado) nao e permitido.
    for name in MODULES:
        for node in ast.walk(_tree(name)):
            if isinstance(node, ast.Attribute):
                assert node.attr != primitive, "%s usa %s" % (name, primitive)


def test_every_network_and_process_call_site_has_an_injectable_seam():
    seams = {"opener", "runner", "status_fn", "probe_fn", "apply_fn",
             "emit", "resolver", "which"}
    offenders = []
    for name in MODULES:
        for function in _functions(_tree(name)):
            if not _mentions(function, "urlopen", "subprocess", "Popen"):
                continue
            params = {arg.arg for arg in
                      list(function.args.args)
                      + list(function.args.kwonlyargs)}
            if params & seams or function.name in SEAM_HELPERS:
                continue
            offenders.append("%s:%s" % (name, function.name))
    assert offenders == []


def test_the_only_subprocess_entry_point_is_the_guarded_installer():
    offenders = []
    for name in ("engineinstall.py", "download.py", "enginedata.py"):
        for function in _functions(_tree(name)):
            for node in ast.walk(function):
                if (isinstance(node, ast.Attribute)
                        and node.attr in ("run", "Popen", "call", "check")
                        and isinstance(node.value, ast.Name)
                        and node.value.id == "subprocess"):
                    if function.name not in SEAM_HELPERS:
                        offenders.append("%s:%s" % (name, function.name))
    assert offenders == []


def test_the_launchers_all_run_the_ownership_guard():
    # Nao existe caminho para um spawn neste modulo sem passar pela guarda:
    # `launch_installer` chama `assert_not_lifecycle` duas vezes (comando
    # montado e comando executado) e `download.py` nao gera processo nenhum.
    tree = _tree("engineinstall.py")
    functions = {f.name: f for f in _functions(tree)}
    assert _mentions(functions["launch_installer"], "assert_not_lifecycle")
    assert _mentions(functions["_run_installer"], "assert_not_lifecycle")


def test_the_advice_puts_the_removal_on_the_owner():
    out = engineinstall.advice()
    assert out["ok"] is True
    assert "Configuracoes" in out["engine"] or "desinstalador" in (
        out["engine"].lower())
    assert "O Thero nao desinstala" in out["engine"]


def test_the_advice_names_the_only_thing_we_can_clean():
    from thero.settings import ENV_MARKER_END, ENV_MARKER_START

    out = engineinstall.advice()
    assert ENV_MARKER_START in out["ours"] and ENV_MARKER_END in out["ours"]
    assert "$PROFILE" in out["ours"]
    assert out["startup"] and "Run" in out["startup"]


def test_the_advice_text_crosses_the_bridge_as_ascii():
    for value in engineinstall.advice().values():
        assert isinstance(value, str) and value.isascii()
```

- [ ] **Step 2: Rodar para ver falhar**

Run: `python -m pytest tests/test_engineinstall_invariants.py -q`
Expected: FAIL — `AttributeError: module 'thero.engineinstall' has no attribute 'advice'`

- [ ] **Step 3: Escrever `advice()`**

No fim de `src/thero/engineinstall.py`:

```python
def advice() -> dict:
    """Remocao: decisao do dono da maquina, explicada sem eufemismo.

    Nada neste modulo apaga motor, modelo, blob, servico ou chave de registro.
    A unica escrita nossa e o bloco de ambiente na `$PROFILE`, e ele e
    delimitado por marcador justamente para que QUALQUER um (o usuario, o
    Thero de amanha) remova aquela regiao sem adivinhar nada.
    """
    return {
        "ok": True,
        "engine": (
            "Desinstalar o Ollama e acao sua, no Windows (Configuracoes > "
            "Aplicativos > Ollama > Desinstalar, ou o desinstalador que ele "
            "deixou na pasta dele). O Thero nao desinstala, nao para servico, "
            "nao mexe no registro e nao apaga nada da maquina dele."),
        "models": (
            "Os modelos ficam na pasta padrao do Ollama (%s). Para liberar "
            "espaco use o proprio Ollama ou apague a pasta: o Thero nao "
            "encosta ai." % enginedata.MODEL_DIR),
        "ours": (
            "O unico texto que nos escrevemos e o bloco de ambiente na "
            "$PROFILE, entre '%s' e '%s'. Se o motor sair e o bloco ficar, "
            "nada quebra: as variaveis so passam a apontar para um host que "
            "nao responde, e o Sentinel recusa falar fora de loopback do "
            "mesmo jeito." % (ENV_MARKER_START, ENV_MARKER_END)),
        "startup": enginedata.AUTOSTART_KEY,
        "hint": START_HINT,
    }
```

- [ ] **Step 4: Rodar para ver passar (novos + Tasks 10-12 inteiras)**

Run: `python -m pytest tests/test_engineinstall_invariants.py tests/test_engineinstall_plan.py tests/test_engineinstall_steps.py tests/test_engineinstall_execute.py -q`
Expected: `65 passed` (13 + 15 + 21 + 16)

Run: `python -m pytest tests/ -q`
Expected: `B + 133` passed

- [ ] **Step 5: Commit local**

```bash
git add src/thero/engineinstall.py tests/test_engineinstall_invariants.py
git commit -m "feat(engineinstall): advice de remocao e invariantes de canal provadas por AST"
```

**Acumulado: B + 133.**

---

### Task 14: Documentar a fronteira no README (sem criar arquivo novo)

Quem ler o README tem de sair sabendo a diferença entre *instalar* e *possuir o processo* — foi exatamente aí que o projeto quase errou.

**Files:**
- Modify: `README.md` (inserir a seção nova depois de "Modelos locais" / antes da seção de integração com Athena; local exato: `grep -n "Modelos locais" README.md`)

- [ ] **Step 1: Escrever a seção**

```markdown
## Motor local: instalar é uma coisa, ter o processo é outra

O Thero instala o Ollama **na máquina**, do mesmo jeito que você instalaria
na mão: o instalador oficial da release, assinado e conferido, abre, faz o
trabalho dele e morre. O motor fica sendo programa seu — start-up dele,
portas dele, atualização dele, modelos na pasta padrão dele.

**O Thero nunca é dono do processo do Ollama.** Ele não inicia, não para, não
reinicia e não mantém o motor. Com o Thero fechado, a IA local continua no
ar. Se o motor não estiver de pé, o Thero avisa e pede para você abri-lo; ele
não sobe o motor por você.

Depois de instalado, o acesso é o de sempre: HTTP em loopback (`127.0.0.1`)
e as variáveis `ATHENA_OLLAMA_HOST`/`ATHENA_OLLAMA_MODEL` e
`SENTINEL_OLLAMA_HOST`/`SENTINEL_OLLAMA_MODEL` no seu `$PROFILE`. Nada de
chave no registro, nada de serviço, nada de porta nossa, nada de binário
dentro do payload do Thero.

Antes de qualquer download, você vê o tamanho (instalador ~1,5 GB; modelos de
2 GB a 52 GB conforme o escolhido) e dá um clique. O que o Thero baixa vai
para uma pasta de trabalho no seu temp, com SHA-256 publicado e assinatura
Authenticode conferidos antes de executar.

Desinstalar o Ollama é decisão sua, no Windows. O Thero não desinstala nada:
no máximo ele informa, e o único texto que ele escreve é o bloco de ambiente
na `$PROFILE`, delimitado por `# >>> thero env >>>` / `# <<< thero env <<<`.
```

- [ ] **Step 2: Rodar a suíte (README não quebra nada, mas a regra é medir)**

Run: `python -m pytest tests/ -q`
Expected: `B + 133` passed

- [ ] **Step 3: Commit local**

```bash
git add README.md
git commit -m "docs(README): fronteira entre instalar o motor e ser dono do processo"
```

**Acumulado: B + 133.**

---

### Task 15: Portão final — medir, limpar, amarrar

- [ ] **Step 1: Suíte completa**

Run: `python -m pytest tests/ -q`
Expected: `B + 133` passed, com `B` da Task 0 (o número absoluto da máquina vai ser outro quando você executar — o que vale é o delta: 133 testes novos, nenhuma falha nova)

Run: `python -m pytest tests/ -q -m "not live" --collect-only 2>&1 | tail -2`
Expected: mesma contagem — nenhum teste deste plano é `live`.

- [ ] **Step 2: Rede e subprocesso só com costura**

Run:

```bash
python - <<'PY'
import ast, pathlib
src = pathlib.Path("src/thero")
for name in ("enginedata.py", "artifactcheck.py", "download.py",
             "engineinstall.py"):
    text = (src / name).read_text(encoding="utf-8")
    hits = [flag for flag in ("subprocess", "urlopen", "urllib.request")
            if flag in text]
    print(name, "ASCII" if text.isascii() else "NAO-ASCII",
          "max-line", max(len(l) for l in text.splitlines()), hits)
PY
```

Expected: todos `ASCII`, `max-line <= 79`; `enginedata.py` sem hits; os demais apenas com os hits que as tasks prescreveram.

- [ ] **Step 3: Confirmar que nada do plano toca em processo/registro/serviço**

Run:

```bash
git diff --name-only HEAD~9..HEAD
```

Expected: apenas `README.md`, `src/thero/{enginedata,artifactcheck,download,engineinstall}.py`, `tests/test_{enginedata,artifactcheck,download,providers_local_non_ollama,engineinstall_*}.py` e este plano. Se `localmodels.py`, `apply.py`, `providers.py`, `bridge.py`, `gui/*` ou qualquer arquivo fora de `thero/` aparecer na lista, **pare e pergunte ao dono** — isso violou a seção 6 (e, no caso de `providers.py`/`localmodels.py`, possivelmente o trabalho de outro agente).

- [ ] **Step 4: Commit local final (se sobrou algo)**

```bash
git status --short
```

Expected: vazio, ou apenas os arquivos deste plano aguardando o "ok" do dono para o commit de evidência da seção 12.

---

## 8. Cobertura do pedido (o que cada task entrega)

| Requisito do dono / da tarefa | Task |
|---|---|
| Estado de instalação manual; nada de portable/pasta nossa/binário embutido | 1, 3, 8 (`_workdir` no temp), 6 (`INSTALLER_ARGS` conservador); tabela "dono do quê" na seção 2 |
| Ciclo de vida é do Ollama; nunca spawnamos/paramos o motor | 11 (`assert_not_lifecycle`, `_run_installer` só do instalador), 12 (passo `engine-up` que **observa**), 13 (teste AST do único ponto de subprocesso), 14 (README) |
| Acesso igual ao de quem configurou na mão (loopback + env) | 11 (`write_consumer_env` → `apply.apply_profile`), 10 (host vem do config, nunca do ambiente) |
| Avisar tamanho + um clique antes de baixar | 5 (mede), 10 (`consentText`, `sizeHuman`, `enoughSpace`), 12 (`consent` chamado antes de qualquer efeito) |
| Descobrir em vez de afirmar | Tasks 1-5, cada uma com comando e o que anotar; nenhuma URL/flag/pasta no código sem a evidência da seção 12 |
| Integridade do download (mínimo honesto e o que fazer quando não existir) | 2 (descobre se há digest publicado), 7 (assinatura fail-closed + digest exigido quando publicado), 12 (relatório com tag + digest + publisher do que rodou) |
| Fluxo completo "falta o engine", com estado visível | 10 → 11 → 12 (`probe` → `plan` → `consent` → download → verify → install → engine-up → models → env) |
| Idempotência e recomeço | 8 (`.part` + `os.replace`; arquivo íntegro já presente não rebaixa), 10 (re-observar), 12 (re-plan após o motor subir; teste `test_a_second_execute_...`); "motor existe → parar e perguntar" no `stopAndAsk` da Task 10 |
| Dono do quê (tabela ação/fazemos/não fazemos) | Seção 2, aplicada nas tasks 6-13 |
| Desinstalação é ação do usuário | 13 (`advice()` + proibição AST de primitivas de remoção) |
| LM Studio sem afrouxar o veto | 9 — **já entregue por outro agente** (`0287c92`: `guard_host`/`has_endpoint_path`/`authState "sem sonda"`); a Task 9 deste plano trava o contrato por teste e prova que `guard_base` continua recusando caminho |
| Dependência da ponte | Seção 4 + `progress`/`consent`/`stream_model` (Tasks 11-12), sem tocar em `bridge.py`/`gui/*` |

**Fora deste plano (declarado, não esquecido):** worker/cancelamento e barra de progresso na GUI (ponte); validação de host no lado da Athena (o veto continua morando em `apply`/`localmodels`/`engineinstall`, e a Athena lê sem validar — Pergunta 3); provedor MCP/CLI para "instalar motor" (a CLI é o caminho do terminal e não foi pedida); remoção programática do bloco da `$PROFILE` (o `advice()` da Task 13 aponta os marcadores e o usuário decide).

---

## Auto-revisão

**1. Cobertura do prescrito.** Ver a tabela da seção 8: os cinco itens da espinha dorsal, as sete frentes de escopo do enunciado e as regras por task (seção 5) têm task correspondente. Dois itens viram **task de descoberta** em vez de afirmação: endereço/nome/flags da instalação (Tasks 1, 3) e tamanho/modelo/pasta/disco (Tasks 4, 5). O que eu **verifiquei nesta sessão** e escrevi como fato com fonte: baseline (416 no início, 442/444 com a árvore em movimento, por isso a cadeia é `B + k` e existe a Task 0), ausência do binário, presença de 13,67 GB de blobs sem motor, redirecionamento com expiração do instalador, existência e formato do `sha256sum.txt`, formato de saída do `Get-AuthenticodeSignature`, as duas armadilhas do PowerShell (`$args[0]`, codepage), espaço livre do `C:` e os tamanhos anunciados de `llama3.2`/`qwen3-coder-next`.

**1b. O que a revisão cortou.** A versão inicial deste plano prescrevia um módulo `localep.py`, um campo `ollamaFamily` e um arquivo de estado `engine-state.json`. Os três foram cortados na revisão: o requisito do LM Studio já estava entregue em `0287c92` (`has_endpoint_path` + `guard_host` + `authState "sem sonda"`) e a idempotência é toda de re-observação da máquina, sem estado nosso. A Task 9 virou task de **verificação com teste de contrato**, não de construção.

**2. Placeholders.** Nenhum "TODO"/"tratar erros"/"similar à Task N". Onde a incerteza é real, existe comando para rodar e um local onde o resultado entra (seção 12). Os três pontos genuinamente indisponíveis hoje estão **marcados como PENDENTE com o teste que continua passando nos dois ramos**: flag silenciosa do instalador (`INSTALLER_ARGS = ()` + teste da Task 6 cobre ambos os casos), tamanho de `qwen2.5-coder:14b` (o `plan()` tem ramo `unknownSizes` + teste na Task 10), e formato da linha de progresso (o `percent_from_line` trata com e sem `%`, testado na Task 11). Nenhum bloco de código do plano depende de correção posterior: o helper `get` de `tests/test_download.py` já está na forma que os chamadores usam (`tmp_path=` como workdir).

**3. Consistência de assinaturas entre tasks.** `artifactcheck.check(path=, expected_sha256=, runner=)` (Task 7) é a chamada que a Task 12 faz via `deps["verify"]`; `download.to_file(url, name, workdir, *, expected_sha256, total_bytes, progress, opener, max_bytes)` (Task 8) é a chamada de `deps["download"]` na Task 12 com as mesmas keywords testadas em `test_execute_passes_the_download_keywords_the_downloader_expects`; `enginedata.checksums_url(tag)` (Task 6) é a única forma de montar a URL da Task 11 (`release_info`), e o teste `test_an_untrusted_tag_never_becomes_a_url` amarra os dois; `engineinstall.plan(portrait=, want=, free_bytes=, on_disk=)` (Task 10) é a mesma chamada do re-planejamento na Task 12; `write_consumer_env(cfg, *, profile, want, seen, apply_fn)` (Task 11) é a mesma de `deps["env"]` (Task 12, chamada `(cfg, seen=seen)`); `localmodels.has_endpoint_path`/`guard_host` (Task 9, já embarcados) sao os unicos classificadores usados na tela, e a regra de "provedor Ollama" de `consumer_env_targets` (Task 11) e declaradamente a mesma de `apply._ollama_base` (preset/id == "ollama") - o teste 8 da Task 9 prova que o `/v1` do LM Studio nunca vira `ATHENA_OLLAMA_HOST`. Nao existem mais `localep.py` nem `providers._ollama_family` neste plano: ambos foram cortados na revisao porque a arvore ja tinha entrega equivalente. As contagens sao deltas de `B` (Task 0), nao numeros absolutos: o 416 que medi no inicio ja e 442/444 com o trabalho dos outros agentes.

---

## Perguntas ao dono (recomendação conservadora já aplicada no plano; ele fica horas ausente)

1. **O default do Sentinel é um download de 52 GB.** `SENTINEL_OLLAMA_MODEL=qwen3-coder-next` medido na biblioteca: 52 GB (`q8_0`: 85 GB). O default da Athena (`llama3.2`) é 2 GB. Aplicado: o `consentText` da Task 10 lista o peso **por modelo** e o `plan()` recusa qualquer download sem espaço livre medido (Task 4); nada é baixado em lote sem clique. Recomendação: trocar o default do Sentinel para um `qwen2.5-coder:14b` (~9 GB) — ou deixar o default atual e aceitar que o primeiro onboarding local dele é um download de 52 GB. Não escolho por ele: o plano roda nos dois casos.

2. **"O modelo não existe" → instalar, e se ele não couber no disco?** Ele mandou instalar quando faltar. Mas "instalar" um modelo de 52 GB numa máquina sem 62 GB livres não é instalação, é promessa quebrada. Aplicado: `plan()` devolve `enoughSpace=False`, `actions=[]` e `msg` com o número (Task 10), e o fluxo **para antes** de pedir o clique. Recomendação: manter (nunca apagar blob alheio para "criar espaço"), e oferecer na tela um segundo clique por modelo (baixar só o da Athena agora).

3. **A Athena lê `ATHENA_OLLAMA_HOST` sem validar host.** O Sentinel valida; a Athena não. Hoje o veto mora em quem escreve (`apply._ollama_base` → `guard_base`) e neste plano também em `engineinstall.consumer_env_targets`. Aplicado: não encostei na Athena (fora do escopo do repo `thero/`). Recomendação: abrir tarefa separada no `athena/` para replicar o veto do Sentinel; até lá, nenhuma linha deste plano permite base remota em caminho escrito pelo Thero.

4. **`OLLAMA_HOST` existe no ambiente da máquina: obedecer ou ignorar?** Regra do projeto diz "não ler valor de variável de ambiente", e a Athena lê `OLLAMA_HOST` para apontar para outro servidor. Aplicado: o host **não** vem do ambiente — vem do provedor Ollama em `config.json`, sempre validado como loopback (Task 10, `probe`/`plan`), e `OLLAMA_HOST` é apenas citada no texto de diagnóstico (Task 13). Recomendação: manter ignorando (loopback fixo = invariante), ou aceitar uma exceção estreita: ler `OLLAMA_HOST` **só** para diagnosticar e nunca para escrever config.

5. **LM Studio: o dono quer que ele funcione, mas ele não atende pelos contratos `*_OLLAMA_HOST`.** Aplicado: o registro sem a sonda Ollama **já está na árvore** (`0287c92`), com a mensagem honesta "sabemos que ele existe, nao sabemos listar os modelos dele" e o veto de host intacto (`guard_base` continua recusando caminho). A Task 9 foi reescrita para **não duplicar**: ela só trava o contrato por teste (inclusive `apply._ollama_base` nunca devolver o `/v1` do LM Studio). Não fiz o LM Studio virar Ollama nem afrouxei host. Recomendação: manter; o Athena/Sentinel continuam consumindo Ollama, e se ele quiser Athena sobre LM Studio é trabalho no `athena/` (fora deste plano).

6. **Onboard via linha de comando (terminal) ou só pela janela?** Aplicado: este plano não cria comando de CLI nem toca na ponte em construção; entrega as funções do motor com callback (`execute`, `stream_model`, `plan`) de forma que a ponte consuma depois (seção 4). Recomendação: ao terminar a ponte, o dono decide se a CLI (`--engine-plan`/`--engine-install`) também expõe o fluxo — uma task de ~30 minutos depois.

7. **Pin de versão: sempre a release mais recente, ou uma versão fixa escolhida?** Aplicado: o fluxo resolve a release corrente em execução (`release_info`, Task 11) e confere contra o `sha256sum.txt` **daquela** tag, registrando a tag executada no relatório (Task 12). Não uso a URL assinada do redirect porque ela expira (Task 1). Recomendação: manter "sempre a mais recente verificada"; se ele quiser reprodutibilidade (mesmo binário em duas máquinas), é pinar `KNOWN_GOOD_TAG`/`KNOWN_GOOD_SHA256` da Task 6 e exigir igualdade no `verdict` da Task 7 — mudança de uma constante, e eu não fiz por conta própria.

8. **Aflag "verificar disco antes de perguntar": o piso de folga é 10 GB.** Aplicado: `DISK_RESERVE_GIB = 10.0` na Task 6, usado no `plan()` (Task 10). Recomendação: manter 10 GB (o Ollama descompacta blobs e o Windows precisa de respiradouro); se ele quiser 20/50, é trocar a constante.

9. **Dependência com o plano do time.** O `2026-09-28-registro-de-equipe.md` referencia `plan: onboarding-motor-local` como inexistente — este arquivo é ele. Não editei aquele plano (está em trabalho de outro agente). Recomendação: ao fechar este, o dono manda atualizar a referência cruzada; nenhuma task daqui depende do time.

10. **Outro trabalho na mesma árvore está iniciando o `ollama serve` como processo desanexado nosso.** Li hoje `src/thero/engineproc.py` (não commitado): `start()`/`restart()` com `Popen([binary, "serve"], DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP)` e `OLLAMA_START_WAIT` em `settings.py`. Isso é o oposto do item 2 da espinha dorsal, não importa o comentário dizendo que "não somos o serviço". Aplicado neste plano: nenhuma task daqui chama `engineproc`, o `wait_for_engine` **observa** e pede ao usuário que abra o Ollama, e `assert_not_lifecycle` continua vetando `serve` em qualquer argv que gerarmos. Recomendação: ou o dono revoga a própria regra (e escreve isso no plano da ponte, com o motivo — ex.: "start em demanda do binário que **o usuário** instalou, sem servir de hosted service"), ou o `engineproc` é cortado para `status`/`stop`=nada e a ponte passa a só reportar "motor parado, abra-o". **Não decidi por ele**: nada neste plano depende daquele módulo.
  **Resolvida pelo dono, e a revogação está escrita** (seção 1.1 deste arquivo,
  com a frase literal dele: *"precisamos apenas checar o status e iniciar ou
  mesmo reiniciar caso necessario (o ollama)"*). O `engineproc.py` da ponte é o
  caminho consentido — filho desanexado, sem handle guardado, gatilho só por
  clique — e a `assert_not_lifecycle` deste plano continua vetando `serve` nos
  argv **destes** módulos, que é o escopo que ela sempre teve (`MODULES`,
  Task 13). Não cortar o módulo, não reabrir a pergunta.

---

## 12. Registro de evidência coletada (alvo das Tasks 1-5)

Preencher na máquina do dono, com o comando executado e a saída real. Estes valores alimentam `enginedata.py` (Task 6) e os textos de recusa (Tasks 10-11). **Não deixar linha em branco ao executar a Task 6.**

**E1 — Fonte do instalador (Task 1)**

```
URL candidata (exata):
Status / Content-Length medido:
Content-Type:
URL final (prefixo antes do "?"):
A URL final expira? (se=/sig=):
Conclusao: pino a porta de entrada + o digest publicado? (sim/nao):
```

**E2 — Integridade publicada (Task 2)**

```
A pagina oficial/doc publica digest? (sha256/checksum/digest encontrados):
Arquivo de digest na release (nome + tamanho):
Tag da release:
Linha do artefato Windows (verbatim):
Formato bate "sha  ./nome"? (sim/nao):
Se NAO houver digest publicado: a travada passa a ser so a assinatura
Authenticode + o digest medido gravado no relatorio? (registrar decisao):
```

**E3 — Empacotador, flags e assinante (Task 3)**

```
Bytes baixados vs. medidos no HEAD:
SHA-256 medido (certutil):
Get-AuthenticodeSignature -> Status|Subject (linha completa):
Marcadores encontrados no binario (Inno Setup / Nullsoft / MSI / WiX):
Flags documentadas pelo empacotador (lista):
Flags documentadas pelo Ollama (lista):
INSTALLER_ARGS adotado (com a fonte de cada flag; vazio = assistente visivel):
```

**E4 — Ciclo de vida e disco (Task 4)**

```
HKCU\...\Run (nome + alvo, ou "nenhuma"):
ScheduledTask contendo Ollama (lista, ou "nenhuma"):
`where ollama` / shutil.which (caminho, ou "ausente"):
Pasta de binarios observada:
Pasta de modelos observada + total de bytes:
Manifests presentes (nomes):
Espaco livre no volume dos blobs (bytes):
OLLAMA_HOST / OLLAMA_MODELS presentes no ambiente? (presenca apenas):
```

**E5 — Tamanho dos modelos e progresso (Task 5)**

```
llama3.2:latest -> tamanho:
qwen3-coder-next (tag escolhida) -> tamanho:
qwen2.5-coder:14b -> tamanho:
Quais desses ja tem manifest na maquina:
Formato das linhas do pull (traz "NN %"? traz completed/total?):
ModeloTimeoutS adotado (0 = sem teto):
```


