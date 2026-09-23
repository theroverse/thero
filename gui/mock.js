/* Thero GUI — MOCK de dados (costura do motor).
   Espelha FACTOS do src/thero/cli.py e dos módulos thero.mcp / thero.publish.
   Na fase 2 este arquivo é substituído pela ponte (TheroHost.ps1 -> python thero.py);
   o app.js não muda. Cada seção declara se é COMANDO (flag real da CLI) ou
   CONFIGURAÇÃO (gravação no config do Thero — superfície nova desta interface). */

window.THERO_MOCK = {
  meta: { version: "v1.1.0", command: "thero", entry: "thero.py", config: "~/.thero/config.json" },

  // estado do ambiente (detectado pelo motor); a UI só reflete
  env: {
    cliInstalled: true,          // primeira abertura => false => roda onboarding
    firstRun: false,
    python: { ok: true, version: "3.12.1", min: "3.10+" },
    node: { ok: true, version: "v20.11.0" },
    claude: { ok: true, authed: true },   // merge exige; skills funcionam sem
    scope: "global",                       // global | local (--local)
    commandInstalled: "thero",             // nome FIXO (settings.DEFAULT_COMMAND_NAME)
    claudeMd: { exists: true },
  },

  // ——— skills do catálogo real (SKILLS do help) + origem ———
  // origin: "thero" = instalada pelo fluxo do Thero (noção de desinstalar bloqueada)
  // origin: "user"  = adicionada/importada pelo usuário (removível)
  skills: [
    { id: "engineering", repo: "Engineering/Reasoning", desc: "Sistema de engenharia e árvore de raciocínio do agente.", installed: true, update: false, origin: "thero" },
    { id: "supabase", repo: "Supabase", desc: "Postgres, migrations, RLS e boas práticas de schema.", installed: true, update: true, origin: "thero" },
    { id: "frontend", repo: "React/Frontend", desc: "Componentes, design system e acessibilidade.", installed: true, update: false, origin: "thero" },
    { id: "agentsinc", repo: "Agents Inc", desc: "Padrões de orquestração de agentes.", installed: false, update: false, origin: "thero" },
    { id: "caveman", repo: "Caveman", desc: "Comunicação comprimida para economizar tokens.", installed: true, update: false, origin: "user" },
    { id: "impeccable", repo: "impeccable", desc: "Craft de interface (instalador próprio: npx impeccable).", installed: false, update: false, origin: "thero", own: true },
    { id: "git-workflow", repo: "git-workflow", desc: "Branching, Conventional Commits, PRs e revisão.", installed: true, update: false, origin: "user" },
  ],

  // resultados de uma busca no catálogo de comunidade (fase 2: npx skills search)
  skillResults: [
    { id: "postgres-optim", repo: "supabase/postgres-optim", desc: "Tuning de query e índices no Postgres." },
    { id: "tailwork", repo: "tailwork", desc: "Tailwind + design tokens sem duplicar CSS." },
    { id: "playwright-e2e", repo: "playwright-e2e", desc: "Escreve testes E2E Playwright a partir de fluxos." },
    { id: "docs-distiller", repo: "docs-distiller", desc: "Resume documentação técnica em convenções." },
  ],

  // ——— provedores de IA: presets pré-definidos, todos editáveis ———
  // authKind: "session" = usa a sessão/login já feito no produto
  //           "apikey"  = chave em variável de ambiente
  //           "local"   = endpoint local, sem chave
  // base vazio = o preset não fixa endpoint (você define ao ativar)
  providerPresets: [
    { id: "claude", name: "Claude (via Claude Code)", kind: "sessão local", authKind: "session", base: "", transport: "claude -p (subprocesso)", models: ["opus", "sonnet", "haiku"], famous: true },
    { id: "openai", name: "OpenAI", kind: "nuvem", authKind: "apikey", base: "https://api.openai.com/v1", transport: "OpenAI-compatível", models: ["gpt-4o", "gpt-4o-mini"], famous: true },
    { id: "anthropic", name: "Anthropic API", kind: "nuvem", authKind: "apikey", base: "https://api.anthropic.com/v1", transport: "Anthropic Messages", models: ["claude-sonnet-4-5", "claude-haiku-4-5"], famous: true },
    { id: "gemini", name: "Google Gemini", kind: "nuvem", authKind: "apikey", base: "https://generativelanguage.googleapis.com/v1beta", transport: "Gemini generateContent", models: ["gemini-2.5-pro", "gemini-2.5-flash"], famous: true },
    { id: "ollama", name: "Ollama (local)", kind: "local", authKind: "local", base: "http://127.0.0.1:11434", transport: "API nativa Ollama", models: ["qwen2.5-coder:14b", "llama3.1:8b"], famous: true },
    { id: "lmstudio", name: "LM Studio (local)", kind: "local", authKind: "local", base: "http://127.0.0.1:1234/v1", transport: "OpenAI-compatível local", models: ["modelo aberto no LM Studio"], famous: true },
    { id: "openrouter", name: "OpenRouter", kind: "roteador", authKind: "apikey", base: "https://openrouter.ai/api/v1", transport: "OpenAI-compatível", models: ["qualquer modelo roteado"], famous: true },
    { id: "omniroute", name: "OmniRoute", kind: "roteador", authKind: "apikey", base: "", transport: "um endpoint, vários modelos atrás", models: ["roteado pelo OmniRoute"], famous: true },
    { id: "mistral", name: "Mistral", kind: "nuvem", authKind: "apikey", base: "https://api.mistral.ai/v1", transport: "OpenAI-compatível", models: ["mistral-large-latest"], famous: true },
    { id: "deepseek", name: "DeepSeek", kind: "nuvem", authKind: "apikey", base: "https://api.deepseek.com", transport: "OpenAI-compatível", models: ["deepseek-chat"], famous: true },
    { id: "groq", name: "Groq", kind: "nuvem", authKind: "apikey", base: "https://api.groq.com/openai/v1", transport: "OpenAI-compatível", models: ["llama-3.3-70b-versatile"], famous: true },
    { id: "azure", name: "Azure OpenAI", kind: "nuvem", authKind: "apikey", base: "https://<recurso>.openai.azure.com", transport: "deploy do seu recurso", models: ["deploy configurado"], famous: false },
    { id: "xai", name: "xAI", kind: "nuvem", authKind: "apikey", base: "https://api.x.ai/v1", transport: "OpenAI-compatível", models: ["grok-4"], famous: false },
    { id: "custom", name: "Manual (qualquer provedor)", kind: "manual", authKind: "apikey", base: "", transport: "OpenAI-compatível ou outro", models: ["definir"], famous: false },
  ],

  // ——— ALVOS: os programas onde o Thero aplica provedor + modelo ———
  // cfg = onde a configuração cai de verdade | writes = se dá para escrever por arquivo
  // skills = se o --publish atual do Thero já escreve nesse alvo
  agentPresets: [
    { id: "claude", name: "Claude Code", kind: "CLI de agente", cfg: "~/.claude/settings.json", format: "json", auth: "login do próprio Claude Code", writes: true, skills: true, famous: true },
    { id: "qoder", name: "Qoder", kind: "IDE/agente", cfg: "configurações do Qoder (modelos + MCP)", format: "próprio", auth: "chave na própria config", writes: true, skills: true, famous: true },
    { id: "opencode", name: "OpenCode", kind: "CLI de agente", cfg: "~/.config/opencode/opencode.json", format: "json", auth: "seção de provider + env", writes: true, skills: true, famous: true },
    { id: "codex", name: "Codex", kind: "CLI de agente", cfg: "~/.codex/config.toml", format: "toml", auth: "login do Codex ou env OPENAI_API_KEY", writes: true, skills: false, famous: true },
    { id: "cline", name: "Cline", kind: "extensão VS Code", cfg: "settings.json do VS Code (namespace cline)", format: "json", auth: "chave por provedor na UI da extensão", writes: true, skills: false, famous: true },
    { id: "vscode", name: "VS Code", kind: "editor", cfg: "settings.json do usuário", format: "json", auth: "delegado à extensão instalada", writes: true, note: "o VS Code recebe provedor/modelo pela extensão (Cline, Continue, Roo) — não por conta própria.", skills: false, famous: true },
    { id: "roocode", name: "Roo Code", kind: "extensão VS Code", cfg: "settings.json do VS Code (namespace Roo)", format: "json", auth: "chave por provedor na UI", writes: true, skills: false, famous: false },
    { id: "gemini-cli", name: "Gemini CLI", kind: "CLI de agente", cfg: "~/.gemini/settings.json", format: "json", auth: "login ou GEMINI_API_KEY", writes: true, skills: false, famous: false },
    { id: "continue", name: "Continue", kind: "extensão IDE", cfg: "~/.continue/config.json", format: "json", auth: "apiKey por provider no arquivo", writes: true, skills: false, famous: false },
    { id: "aider", name: "Aider", kind: "CLI de agente", cfg: "~/.aider.conf.yml", format: "yml", auth: "env por provedor", writes: true, skills: false, famous: false },
    { id: "zed", name: "Zed", kind: "editor", cfg: "~/.config/zed/settings.json", format: "json", auth: "variável de ambiente por provedor", writes: true, skills: false, famous: false },
    { id: "cursor", name: "Cursor", kind: "IDE", cfg: "ajustes da IDE", format: "—", auth: "conta Cursor; provedor próprio", writes: false, note: "a IDE não expõe provedor por arquivo: aqui o Thero só registra o modelo recomendado.", skills: false, famous: true },
    { id: "manual", name: "Manual (qualquer programa)", kind: "manual", cfg: "definir caminho", format: "a definir", auth: "definir", writes: true, skills: false, famous: false },
  ],

  agents: [
    { preset: "claude", label: "Claude Code", cfg: "~/.claude/settings.json", format: "json", provider: "claude", model: "sonnet", enabled: true, status: "em dia", skills: true, origin: "thero", note: "o Thero já usa este programa para merge e indexação" },
    { preset: "qoder", label: "Qoder", cfg: "configurações do Qoder", format: "próprio", provider: "openai", model: "gpt-4o", enabled: true, status: "pendente", skills: true, origin: "user" },
    { preset: "opencode", label: "OpenCode", cfg: "~/.config/opencode/opencode.json", format: "json", provider: "ollama", model: "qwen2.5-coder:14b", enabled: true, status: "em dia", skills: true, origin: "user" },
  ],


  // provedores já configurados (pré-definidos no primeiro uso; o usuário edita)
  providers: [
    { preset: "claude", label: "Claude Code", base: "", authKind: "session", authVar: "", transport: "claude -p (subprocesso)", model: "sonnet", enabled: true, origin: "thero", authState: "sessão ativa",
      roles: { athena: true, sentinel: false }, lastCheck: "sessão confirmada hoje" },
    { preset: "openai", label: "OpenAI", base: "https://api.openai.com/v1", authKind: "apikey", authVar: "THERO_OPENAI_API_KEY", transport: "OpenAI-compatível", model: "gpt-4o", enabled: true, origin: "user", authState: "aguardando chave",
      roles: { athena: false, sentinel: true }, lastCheck: "variável não definida" },
    { preset: "ollama", label: "Ollama (local)", base: "http://127.0.0.1:11434", authKind: "local", authVar: "", transport: "API nativa Ollama", model: "qwen2.5-coder:14b", enabled: true, origin: "user", authState: "registrado",
      roles: { athena: true, sentinel: true }, lastCheck: "servidor respondeu" },
  ],

  // modelos locais (o que a Athena e o Sentinel chamam quando o provedor é local)
  localModels: [
    { id: "qwen25-coder-14b", provider: "ollama", name: "qwen2.5-coder:14b", ctx: "32k", size: "9.0 GB", status: "pronto", usedBy: ["athena"] },
    { id: "llama31-8b", provider: "ollama", name: "llama3.1:8b", ctx: "128k", size: "4.9 GB", status: "pronto", usedBy: ["sentinel"] },
    { id: "deepseek-r1-8b", provider: "ollama", name: "deepseek-r1:8b", ctx: "64k", size: "5.1 GB", status: "ausente", usedBy: [] },
    { id: "lmstudio-loaded", provider: "lmstudio", name: "Modelo aberto no LM Studio", ctx: "definido pelo app", size: "—", status: "desconhecido", usedBy: [] },
  ],

  // quem consome o quê (o Thero define; Athena e Sentinel executam)
  consumers: [
    { id: "athena", name: "Athena", task: "Indexar arquitetura e responder sobre o índice", note: "roda em lote sobre muitos arquivos: prioriza custo e contexto longo." },
    { id: "sentinel", name: "Sentinel", task: "Análise de estado do sistema e alertas", note: "chamadas curtas e frequentes: prioriza latência." },
  ],

  // ——— ferramentas expostas pelo servidor MCP (mcp/capabilities.py) ———
  mcpTools: [
    { name: "athena_index", app: "athena", desc: "Indexa a arquitetura do projeto em ./.athena." },
    { name: "athena_recall", app: "athena", desc: "Consulta o índice de memória/arquitetura." },
    { name: "athena_remember", app: "athena", desc: "Grava uma nota/convenção no índice." },
    { name: "zeus_plan", app: "zeus", desc: "Planeja uma tarefa contra o índice da Athena." },
    { name: "thero_audit", app: "thero", desc: "Audita o projeto atual (somente leitura)." },
  ],

  // agentes-alvo do --publish (publish/installer.py)
  publishAgents: [
    { id: "claude", name: "Claude Code", base: "~/.claude/skills", kind: "SKILL.md", on: true, env: "" },
    { id: "qoder", name: "Qoder", base: "~/.qoder/skills", kind: "SKILL.md", on: true, env: "THERO_QODER_SKILLS_DIR" },
    { id: "opencode", name: "OpenCode", base: "~/.config/opencode/command", kind: "comando .md", on: false, env: "THERO_OPENCODE_CMD_DIR" },
  ],

  // ——— referência de Comandos: cada flag/subcomando real do cli.py ———
  // what/why/how vem do HELP_EPILOG e da implementação; nada aqui é novo.
  commands: [
    {
      id: "full", flag: "(sem argumentos)", name: "Fluxo completo", kind: "default",
      what: "Instala as skills, consolida o CLAUDE.md global e instala/atualiza o comando de atalho.",
      why: "É o caminho de uma sentado: você aponta a versão portable e o Thero configura o resto.",
      how: [
        { cmd: "python thero.py", note: "escopo global (~/.claude)" },
        { cmd: "python thero.py --local", note: "só na pasta do projeto (./.claude)" },
      ],
      requires: "Python 3.10+ · Node/npx para skills",
    },
    {
      id: "skills-only", flag: "--skills-only", name: "Só as skills", kind: "flag",
      what: "Instala apenas as skills, sem tocar no CLAUDE.md nem no comando de atalho.",
      why: "Você quer a stack de skills mas o CLAUDE.md já está do jeito que você quer.",
      how: [{ cmd: "python thero.py --skills-only", note: "falhas individuais viram SKILLS_INSTALL_FAILED.md" }],
      requires: "Node/npx · funciona sem Claude Code",
    },
    {
      id: "merge-only", flag: "--merge-only", name: "Só o CLAUDE.md", kind: "flag",
      what: "Consolida apenas o CLAUDE.md global (backup com timestamp, merge, validação, substituição atômica).",
      why: "Reaplicar o Engineering OS sem reinstalar nada.",
      how: [{ cmd: "python thero.py --merge-only", note: "idempotente: não duplica o bloco" }],
      requires: "Claude Code autenticado",
    },
    {
      id: "audit-only", flag: "--audit-only", name: "Auditar sem instalar", kind: "flag",
      what: "Audita o projeto atual em somente leitura e gera CLAUDE_AUDIT.md; não instala nada.",
      why: "Ver o estado do projeto antes de decidir qualquer configuração.",
      how: [{ cmd: "python thero.py --audit-only", note: "severidades: CRITICAL · BUG · RISK · MAINTENANCE · IMPROVEMENT" }],
      requires: "Claude Code autenticado",
    },
    {
      id: "audit", flag: "--audit", name: "Configurar e auditar", kind: "flag",
      what: "Executa o fluxo completo e, em seguida, audita o projeto atual.",
      why: "Configure e receba o diagnóstico do projeto no mesmo passo.",
      how: [{ cmd: "python thero.py --audit", note: "ordem garantida: instala → audita" }],
      requires: "Claude Code autenticado",
    },
    {
      id: "local", flag: "--local", name: "Escopo local", kind: "modificador",
      what: "Modificador: tudo vai para a pasta atual (./.claude) em vez do usuário (~/.claude).",
      why: "Provar a stack num projeto específico sem alterar o ambiente global.",
      how: [{ cmd: "python thero.py --local", note: "vale para skills, merge e comando" }],
      requires: "—",
    },
    {
      id: "index", flag: "--index", name: "Rodar a Athena", kind: "flag",
      what: "Roda a Athena (indexador de arquitetura) na pasta atual, se estiver instalada. Não instala skills nem mexe no CLAUDE.md.",
      why: "O índice em ./.athena deixa o CLAUDE.md consultar resumos em vez de reler tudo.",
      how: [
        { cmd: "python thero.py --index", note: "indexa a pasta atual" },
        { cmd: "python thero.py --index --max-files 400", note: "limite de segurança de arquivos" },
      ],
      requires: "Athena ao lado do thero, THERO_ATHENA_PATH, ou clone automático em ~/.thero/tools/",
    },
    {
      id: "max-files", flag: "--max-files N", name: "Limite da Athena", kind: "modificador",
      what: "Modificador de --index: teto de arquivos a indexar.",
      why: "Evita indexar um monorepo inteiro por engano numa primeira rodada.",
      how: [{ cmd: "python thero.py --index --max-files 200", note: "comece baixo, suba quando o resumo fizer sentido" }],
      requires: "usar com --index",
    },
    {
      id: "plan", flag: "--plan TAREFA", name: "Rodar o Zeus", kind: "flag",
      what: "Roda o Zeus para planejar TAREFA contra o índice da Athena. Não instala nada.",
      why: "Plano candidato antes de codar: escreve .claude/zeus-plan.md.",
      how: [
        { cmd: 'python thero.py --plan "adicionar campo de telefone no cadastro"', note: "sempre entre aspas se tiver espaço" },
        { cmd: 'python thero.py --plan "refatorar auth" --plan-context ../monorepo', note: "contexto = raiz do monorepo, para seguir convenções irmãs" },
      ],
      requires: "Zeus (instala/atualiza automaticamente com confirmação) · claude -p",
    },
    {
      id: "plan-context", flag: "--plan-context PASTA", name: "Contexto do Zeus", kind: "modificador",
      what: "Modificador de --plan: indexa essa pasta para os resumos.",
      why: "O plano é escrito na pasta atual, mas lê as convenções de outro lugar.",
      how: [{ cmd: "python thero.py --plan \"…\" --plan-context /caminho/raiz", note: "não muda o destino do plano" }],
      requires: "usar com --plan",
    },
    {
      id: "check", flag: "--check", name: "Verificar updates", kind: "flag",
      what: "Verifica se alguma skill instalada tem atualização disponível. Não muda nada.",
      why: "Saber antes de atualizar — a checagem é somente leitura.",
      how: [{ cmd: "python thero.py --check", note: "cobre npx skills e impeccable" }],
      requires: "—",
    },
    {
      id: "update", flag: "--update", name: "Atualizar skills", kind: "flag",
      what: "Atualiza as skills instaladas para a versão mais recente. Não mexe no CLAUDE.md nem no comando.",
      why: "Manter a stack no最新版 sem reconfigurar o ambiente.",
      how: [{ cmd: "python thero.py --update", note: "rode --check antes para ver o escopo" }],
      requires: "Node/npx",
    },
    {
      id: "mcp", flag: "--mcp", name: "Servidor MCP", kind: "flag",
      what: "Serve o MCP server do Theroverse em stdio (JSON-RPC), expondo Athena/Zeus/Thero como ferramentas para qualquer agente MCP.",
      why: "Um registro serve Claude Code, OpenCode e Qoder ao mesmo tempo, sem duplicar scripts.",
      how: [
        { cmd: "python thero.py --mcp", note: "bloqueia lendo stdin; stdout é puro JSON-RPC" },
        { cmd: "thero --mcp", note: "mesma coisa pelo atalho, de qualquer pasta" },
      ],
      requires: "Python 3.10+ · projeto alvo é o cwd (ou --project-dir)",
    },
    {
      id: "publish", flag: "--publish", name: "Publicar skills/comandos", kind: "flag",
      what: "Escreve as skills/comandos first-party nos diretórios nativos de cada agente (mesmo registro do --mcp).",
      why: "Onde MCP não está ativo, o arquivo nativo resolve — com o caminho do CLI já resolvido.",
      how: [
        { cmd: "python thero.py --publish", note: "todos os agentes do registro" },
        { cmd: "python thero.py --publish --publish-agent qoder,opencode", note: "subconjunto por agente" },
        { cmd: "python thero.py --publish --publish-out ./out", note: "pasta própria em vez do diretório nativo" },
      ],
      requires: "skills/agentes instaláveis; itens irresolvíveis são pulados com aviso",
    },
    {
      id: "publish-agent", flag: "--publish-agent LISTA", name: "Agentes-alvo", kind: "modificador",
      what: "Modificador de --publish: escolhe claude, qoder, opencode (ou all), separados por vírgula.",
      why: "Publicar só no agente que você usa evita arquivos órfãos no home.",
      how: [{ cmd: "python thero.py --publish --publish-agent claude", note: "claude/qoder → SKILL.md · opencode → comando .md" }],
      requires: "usar com --publish",
    },
    {
      id: "publish-out", flag: "--publish-out DIR", name: "Saída da publicação", kind: "modificador",
      what: "Modificador de --publish: escreve em DIR em vez do diretório nativo de cada agente.",
      why: "Gerar um pacote para revisão antes de encostar no home.",
      how: [{ cmd: "python thero.py --publish --publish-out ./build/skills", note: "struture DIR por agente na revisão" }],
      requires: "usar com --publish",
    },
    {
      id: "shortcut", flag: "thero …", name: "Atalho no PATH", kind: "atalho",
      what: "O fluxo completo instala automaticamente o comando de atalho, sempre chamado thero — sem renomear.",
      why: "Rodar o Thero de qualquer pasta, sem lembrar o caminho da versão portable.",
      how: [
        { cmd: "thero skills", note: "atalho → --skills-only" },
        { cmd: "thero audit", note: "atalho → auditoria do projeto atual" },
        { cmd: "thero --mcp", note: "linha de registro do servidor MCP no agente" },
      ],
      requires: "PowerShell ($PROFILE) no Windows · bash/zsh no macOS/Linux · reabrir o terminal",
    },
  ],

  // ——— linhas de log que o motor emitiria (stdout real na fase 2) ———
  runLog: [
    { t: "info", s: "Thero {version} · escopo {scope}" },
    { t: "act", s: "{actionLine}" },
    { t: "muted", s: "executando: {cmd}" },
    { t: "ok", s: "concluído sem erros" },
  ],

  configLog: [
    { t: "info", s: "lendo {config}" },
    { t: "act", s: "{actionLine}" },
    { t: "muted", s: "validando: {cmd}" },
    { t: "ok", s: "config gravada · sem toque em CLI" },
  ],
};
