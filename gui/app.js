/* Thero GUI — controlador (mock).
   Duas naturezes de tela, declaradas em SECTIONS[].kind:
     "cli"    = reflete flags reais do src/thero/cli.py (rodar o motor)
     "config" = parametrização desta interface (provedores/modelos) — grava config
     "none"   = referência documentada, nada é executado
   A única costura com o motor é Bridge.*; hoje resolve contra THERO_MOCK. */

(function () {
  "use strict";
  const M = window.THERO_MOCK;
  const E = M.env;

  const IC = {
    status: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M12 20a8 8 0 1 0-8-8"/><path d="M12 12l4-2" stroke-linecap="round"/><circle cx="12" cy="12" r="1.4" fill="currentColor" stroke="none"/></svg>',
    skills: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"><path d="m12 3 8 4.5-8 4.5-8-4.5z"/><path d="m4 12 8 4.5 8-4.5"/><path d="m4 16.5 8 4.5 8-4.5"/></svg>',
    doc: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"><path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4M9 12h6M9 16h6"/></svg>',
    plug: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><path d="M9 3v5M15 3v5"/><path d="M7 8h10v3a5 5 0 0 1-10 0z"/><path d="M12 16v5"/></svg>',
    send: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"><path d="m4 12 16-7-6 16-3-6z"/></svg>',
    cmd: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="m6 8 4 4-4 4"/><path d="M13 16h5"/></svg>',
    cpu: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"><rect x="7" y="7" width="10" height="10" rx="2"/><path d="M4 10h3M4 14h3M17 10h3M17 14h3M10 4v3M14 4v3M10 17v3M14 17v3" stroke-linecap="round"/></svg>',
    layers: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"><rect x="3" y="4" width="18" height="5" rx="1.5"/><rect x="3" y="11" width="18" height="5" rx="1.5"/><path d="M6 19.5h12" stroke-linecap="round"/></svg>',
    target: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="3.5" y="4" width="17" height="13" rx="2"/><path d="M8 20.5h8" stroke-linecap="round"/><path d="M12 17v3.5" stroke-linecap="round"/><path d="M7.5 10.5h4" stroke-linecap="round"/></svg>',
    search: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"><circle cx="11" cy="11" r="6"/><path d="m20 20-3.6-3.6"/></svg>',
    plus: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>',
    trash: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M5 8h14M9 8V5h6v3M7 8l1 12h8l1-12"/></svg>',
    lock: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linejoin="round"><rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg>',
    download: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4v11m0 0 4-4m-4 4-4-4"/><path d="M5 19h14"/></svg>',
    check: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>',
    x: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M6 6l12 12M18 6 6 18"/></svg>',
    info: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01" stroke-linecap="round"/></svg>',
  };

  const el = (id) => document.getElementById(id);
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  const SECTIONS = [
    { id: "status", group: "Ambiente", label: "Status", icon: "status", kind: "cli" },
    { id: "providers", group: "Provedores e modelos", label: "Provedores de IA", icon: "cpu", kind: "config" },
    { id: "models", group: "Provedores e modelos", label: "Modelos locais", icon: "layers", kind: "config" },
    { id: "agents", group: "Provedores e modelos", label: "Programas alvo", icon: "target", kind: "config" },
    { id: "skills", group: "Stack", label: "Skills", icon: "skills", kind: "cli" },
    { id: "claude", group: "Stack", label: "CLAUDE.md", icon: "doc", kind: "cli" },
    { id: "mcp", group: "Integração", label: "Theroverse MCP", icon: "plug", kind: "cli" },
    { id: "publish", group: "Integração", label: "Publicar skills", icon: "send", kind: "cli" },
    { id: "commands", group: "Referência", label: "Comandos", icon: "cmd", kind: "none" },
  ];

  const state = {
    scope: E.scope,
    section: "status",
    providerSel: 0,
    providerDraft: null,          // edição em curso de um provedor
    agentSel: 0,
    agentDraft: null,             // programa novo (ainda não gravado na lista)
    agentQuery: "",
    presetQuery: "",
    skillQuery: "",
    skillResults: null,
    importPath: "",
    cmdQuery: "",
    publishAgents: new Set(M.publishAgents.filter((a) => a.on).map((a) => a.id)),
    publishOut: "",
    routing: { athena: "qwen2.5-coder:14b", sentinel: "llama3.1:8b", fallback: "Claude Code" },
    routingMode: "zeus",             // "zeus" = ele decide | "fixo" = padrão por ferramenta
  };
  const isLocal = () => state.scope === "local";
  const kindOf = (id) => (SECTIONS.find((s) => s.id === id) || {}).kind;

  // ——— linha do rodapé: comando real OU gravação de config ———
  function cmd(flags) { return "python " + M.meta.entry + (flags ? " " + flags : "") + (isLocal() ? " --local" : ""); }
  function cfg(what) { return M.meta.config + " → " + what; }

  function defaultCmd() {
    switch (state.section) {
      case "skills": return cmd("--update");
      case "claude": return cmd("--merge-only");
      case "mcp": return cmd("--mcp");
      case "publish": return cmd("--publish" + (state.publishAgents.size ? " --publish-agent " + [...state.publishAgents].join(",") : "") + (state.publishOut ? " --publish-out " + state.publishOut : ""));
      case "agents": {
        const x = draftAgent();
        return x ? cfg("agents[" + x.label.toLowerCase().replace(/\s+/g, "-") + "] → " + (x.provider || "sem provedor")) : cfg("agents[]");
      }
      case "providers": {
        const p = currentProvider();
        return p ? cfg("providers[" + (p.label || "…").toLowerCase().replace(/\s+/g, "-") + "]") : cfg("providers[]");
      }
      case "models": return cfg("routing.athena = " + state.routing.athena + " · routing.sentinel = " + state.routing.sentinel);
      case "commands": return "";
      default: return cmd("");
    }
  }
  function currentProvider() { return M.providers[state.providerSel] || null; }
  function draftOf() { return state.providerDraft || currentProvider(); }
  function currentAgent() { return M.agents[state.agentSel] || null; }
  function draftAgent() { return state.agentDraft || currentAgent(); }
  function authKindOf(p) { return p.authKind || (M.providerPresets.find((x) => x.id === p.preset) || {}).authKind || "apikey"; }
  function authNote(p) {
    const k = authKindOf(p);
    if (k === "session") return "o login é feito no próprio produto; ao Thero basta confirmar a sessão ativa";
    if (k === "local") return "endpoint local: dispensa chave enquanto o servidor estiver no ar";
    return p.authVar ? "chave lida da variável " + p.authVar + " — o Thero guarda só o nome, nunca o valor" : "defina o nome da variável acima e registre para o Thero conseguir ler a chave";
  }

  function syncCmd() {
    const c = defaultCmd();
    const isCfg = kindOf(state.section) === "config";
    el("cmdbar-hint").textContent = isCfg ? "grava no config do Thero" : (state.section === "commands" ? "referência — nada roda aqui" : "comando montado pelas opções");
    el("cmd-preview").innerHTML = (c ? esc(c) : "—").replace(/(--[\w-]+)/g, '<span class="flag">$1</span>');
    const run = el("btn-run");
    run.textContent = isCfg ? "Salvar" : "Executar";
    run.disabled = !c;
    el("btn-copy").disabled = !c;
  }

  // ————————————————— SIDEBAR —————————————————
  function renderSidebar() {
    const groups = {};
    SECTIONS.forEach((s) => (groups[s.group] = groups[s.group] || []).push(s));
    let h = "";
    for (const [g, items] of Object.entries(groups)) {
      h += `<div class="side-group"><div class="side-group-label">${esc(g)}</div>`;
      h += items.map((s) => `<button class="side-item${s.id === state.section ? " is-current" : ""}" data-go="${s.id}">
        <span class="side-ico">${IC[s.icon]}</span><span>${esc(s.label)}</span><span class="side-flag">${s.kind === "config" ? "config" : s.kind === "none" ? "docs" : "cli"}</span></button>`).join("");
      h += `</div>`;
    }
    el("sidebar").innerHTML = h;
    el("sidebar").querySelectorAll("[data-go]").forEach((b) => b.addEventListener("click", () => go(b.dataset.go)));
  }
  function go(id) { state.section = id; state.providerDraft = null; state.agentDraft = null; render(); }

  function head(icon, title, flag) {
    return `<div class="sec-head"><span class="sec-ico">${IC[icon]}</span><div class="sec-title"><h1>${esc(title)}</h1>${flag ? `<span class="sec-flag">${esc(flag)}</span>` : ""}</div></div>`;
  }

  // ————————————————— SEÇÕES —————————————————
  const sec = {};

  sec.status = () => {
    const row = (label, ok, detail) => `<div class="row" style="cursor:default"><span class="pill ${ok ? "ok" : "err"}">${ok ? "ok" : "—"}</span><div class="row-body"><span class="row-title">${esc(label)}</span><span class="row-sub">${esc(detail)}</span></div></div>`;
    const on = M.providers.filter((p) => p.enabled);
    return `<div class="section">
      ${head("status", "Status do ambiente", "")}
      <p class="lede">Pré-requisitos detectados pela CLI e o estado do que você parametrizou. Escopo atual: <b>${isLocal() ? "Local (pasta do projeto)" : "Global (~)"}</b>.</p>
      <div class="stat-grid block">
        <div class="stat"><div class="k">Python</div><div class="v">${E.python.ok ? esc(E.python.version) : "ausente"}</div><div class="m">mínimo ${esc(E.python.min)}</div></div>
        <div class="stat"><div class="k">Node / npx</div><div class="v">${E.node.ok ? esc(E.node.version) : "ausente"}</div><div class="m">necessário p/ skills</div></div>
        <div class="stat"><div class="k">Claude Code</div><div class="v">${E.claude.ok ? (E.claude.authed ? "autenticado" : "sem auth") : "ausente"}</div><div class="m">merge exige auth</div></div>
        <div class="stat"><div class="k">Atalho</div><div class="v">thero</div><div class="m">${E.commandInstalled ? "instalado automaticamente" : "instala com o fluxo completo"}</div></div>
      </div>
      <div class="block"><div class="block-label">Provedores ativos</div><div class="rows">
        ${on.map((p) => `<div class="row" style="cursor:default"><div class="row-body"><span class="row-title">${esc(p.label)}</span><span class="row-sub">${esc(p.model || "sem modelo")} · ${esc(p.transport)}</span></div>
          <span class="row-tag">${["Athena", "Sentinel"].filter((k) => p.roles[k.toLowerCase()]).join(" · ") || "sem consumo"}</span></div>`).join("") || '<div class="hint">Nenhum provedor ativo — defina em <b>Provedores de IA</b>.</div>'}
      </div></div>
      <div class="block"><div class="block-label">Detalhes</div><div class="rows">
        ${row("CLAUDE.md alvo", E.claudeMd.exists, isLocal() ? "./CLAUDE.md" : "~/.claude/CLAUDE.md")}
        ${row("Skills instaladas", true, M.skills.filter((s) => s.installed).length + " no total · " + M.skills.filter((s) => s.installed && s.origin === "user").length + " suas")}
        ${row("Modelos locais prontos", true, M.localModels.filter((m) => m.status === "pronto").length + " disponíveis para Athena/Sentinel")}
        ${row("Programas com a configuração", M.agents.some((x) => x.status === "em dia"), M.agents.filter((x) => x.status === "em dia").length + " de " + M.agents.length + " em dia · " + M.agents.filter((x) => x.status === "pendente").length + " pendente(s)")}
      </div></div>
      <div class="banner info">${IC.info}<div>Aqui você parametriza o Thero. O que cada ferramenta faz com essa definição vive na interface dela — a Athena lista os projetos indexados, o Zeus edita cenários e fluxos.</div></div>
      <div class="banner info">${IC.info}<div>Sem configuração ainda? Rode o <b>onboarding de primeira abertura</b>. <button class="btn btn-ghost btn-sm" id="sim-first" style="margin-left:8px">Simular 1ª execução</button></div></div>
    </div>`;
  };

  // ——— Provedores de IA: presets + edição + adição manual ———
  sec.providers = () => {
    const p = draftOf();
    const q = state.presetQuery.trim().toLowerCase();
    const presets = M.providerPresets.filter((x) => !q || (x.name + " " + x.kind + " " + x.id).toLowerCase().includes(q));
    return `<div class="section section-wide">
      ${head("cpu", "Provedores de IA", "")}
      <p class="lede">O Thero é onde você define <b>quem responde</b>: provedores de IA e modelos locais, já preenchidos e editáveis. <b>Onde</b> essa definição se aplica (Qoder, Claude Code, OpenCode, VS Code…) você marca em <button class="linklike" data-go="agents">Programas alvo</button>.</p>

      <div class="block"><div class="block-label">Configurados</div><div class="rows">
        ${M.providers.map((x, i) => `<div class="row${i === state.providerSel ? " is-on" : ""}" data-prov="${i}">
          <span class="box"></span><div class="row-body"><span class="row-title">${esc(x.label)}${x.enabled ? "" : " · desabilitado"}</span>
            <span class="row-sub">${esc(x.model || "sem modelo")}${x.base ? " · " + esc(x.base) : ""} · ${esc(x.lastCheck)}</span></div>
          <span class="pill ${x.authState === "aguardando chave" ? "warn" : "ok"}">${esc(x.authState)}</span>
          <span class="row-tag">${["Athena", "Sentinel"].filter((k) => x.roles[k.toLowerCase()]).join(" · ")}</span>
          <span class="origin${x.origin === "thero" ? " is-thero" : ""}">${x.origin === "thero" ? "Thero" : "Sua"}</span></div>`).join("")}
      </div></div>

      ${p ? `<div class="block card"><div class="block-label">Editar — ${esc(p.label || "novo provedor")}</div>
        <div class="field"><label for="pv-label">Nome exibido</label><input class="input" id="pv-label" value="${esc(p.label)}"></div>
        <div class="field" style="margin-top:14px"><label for="pv-base">Endpoint</label><input class="input mono" id="pv-base" placeholder="https://… ou http://127.0.0.1:…" value="${esc(p.base)}">
          <div class="hint">${p.authKind === "local" || p.kind === "local" ? "provedor local: sem chave" : esc(p.transport)}</div></div>
        <div class="field" style="margin-top:14px"><label for="pv-var">Variável com a chave</label><input class="input mono" id="pv-var" placeholder="ex.: THERO_OPENAI_API_KEY" value="${esc(p.authVar)}">
          <div class="hint">o Thero guarda só o <b>nome</b> da variável; a chave continua no seu ambiente.</div></div>
        <div class="field" style="margin-top:14px"><label for="pv-model">Modelo</label><input class="input mono" id="pv-model" list="pvmodels" value="${esc(p.model)}">
          <datalist id="pvmodels">${(M.providerPresets.find((x) => x.id === p.preset) || { models: [] }).models.map((m) => `<option value="${esc(m)}"></option>`).join("")}</datalist></div>
        <div class="block-label" style="margin:20px 0 10px">Autenticação</div>
        <div class="auth-row">
          <span class="pill ${p.authState === "registrado" ? "ok" : p.authState === "sessão ativa" ? "ok" : "warn"}">${esc(p.authState || "não registrado")}</span>
          <div class="row-body"><span class="row-sub">${esc(authNote(p))}</span></div>
          <button class="btn btn-ghost btn-sm" id="pv-auth">${p.authKind === "session" || (M.providerPresets.find((x) => x.id === p.preset) || {}).authKind === "session" ? "Abrir login" : "Registrar chave"}</button>
        </div>
        <div class="block-label" style="margin:20px 0 10px">Quem usa este provedor</div>
        <div class="chip-grid">
          <button class="chip${p.roles.athena ? " is-on" : ""}" data-role="athena">Athena</button>
          <button class="chip${p.roles.sentinel ? " is-on" : ""}" data-role="sentinel">Sentinel</button>
        </div>
        <div class="switch-row block" style="margin-top:16px"><div class="row-body"><span class="row-title">Ativo</span><span class="row-sub">desligado, o provedor fica de fora do roteamento sem perder a configuração</span></div>
          <button class="switch" id="pv-on" role="switch" aria-checked="${p.enabled ? "true" : "false"}" aria-label="Ativar provedor"></button></div>
        <div class="chip-grid block">
          <button class="btn btn-primary" id="pv-save">Salvar</button>
          <button class="btn btn-ghost" id="pv-test">Testar conexão</button>
          ${p.origin === "user" || state.providerDraft ? `<button class="btn btn-ghost" id="pv-del">${IC.trash} Remover</button>` : `<button class="btn btn-ghost" disabled title="instalado pelo Thero: desative em vez de remover">${IC.lock} Não removível</button>`}
          ${state.providerDraft ? `<button class="btn btn-ghost" id="pv-cancel">Cancelar</button>` : ""}
        </div>
        <div class="hint" id="pv-test-result"></div>
      </div>` : `<div class="banner info block">${IC.info}<div>Selecione um provedor para editar endpoint, chave, modelo e quem o consome.</div></div>`}

      <div class="block"><div class="block-label">Adicionar a partir de um preset</div>
        <div class="search-row"><span>${IC.search}</span><input class="input mono" id="preset-q" placeholder="filtrar provedores (openai, gemini, ollama…)" value="${esc(state.presetQuery)}"></div>
        <div class="preset-grid">${presets.map((x) => `<button class="preset" data-preset="${x.id}">
            <span class="preset-name">${esc(x.name)}</span><span class="preset-meta">${esc(x.kind)}</span><span class="preset-sub">${x.base ? esc(x.base) : "endpoint definido por você"}</span></button>`).join("")}</div>
        <div class="hint">Tudo que o preset traz é editável depois. Não acha o seu? Use <b>Manual</b> e informe qualquer endpoint compatível.</div>
      </div>
    </div>`;
  };

  // ——— Programas-alvo: onde o Thero escreve provedor + modelo ———
  sec.agents = () => {
    const enabledProviders = M.providers.filter((p) => p.enabled);
    const a = draftAgent();
    const q = state.agentQuery.trim().toLowerCase();
    const presets = M.agentPresets.filter((x) => !q || (x.name + " " + x.kind + " " + x.cfg).toLowerCase().includes(q));
    const statusPill = (s) => `<span class="pill ${s === "em dia" ? "ok" : s === "pendente" ? "warn" : "err"}">${esc(s)}</span>`;
    return `<div class="section section-wide">
      ${head("target", "Programas que usam o Thero", "")}
      <p class="lede">Aqui você marca <b>onde</b> a configuração vai cair: um programa ou vários. Cada um recebe provedor e modelo da lista de Provedores de IA; o que o Thero escreve é o arquivo nativo daquele programa — nunca a sua chave.</p>

      <div class="block"><div class="block-label">Selecionados</div><div class="rows">
        ${M.agents.map((x, i) => `<div class="row${i === state.agentSel && !state.agentDraft ? " is-on" : ""}" data-agent-row="${i}">
          <span class="box"></span><div class="row-body"><span class="row-title">${esc(x.label)}</span>
            <span class="row-sub mono">${esc(x.cfg)} · ${esc(x.format)}</span>
            <span class="row-sub">provedor <b>${esc(x.provider || "—")}</b> · modelo <b>${esc(x.model || "—")}</b></span></div>
          ${statusPill(x.status)}
          <span class="origin${x.origin === "thero" ? " is-thero" : ""}">${x.origin === "thero" ? "Thero" : "Sua"}</span></div>`).join("") || '<div class="hint">Nenhum programa selecionado ainda.</div>'}
      </div></div>

      ${a ? `<div class="block card"><div class="block-label">${state.agentDraft ? "Novo programa" : "Editar"} — ${esc(a.label || "…")}</div>
        <div class="field"><label for="ag-label">Nome exibido</label><input class="input" id="ag-label" value="${esc(a.label)}"></div>
        <div class="field" style="margin-top:14px"><label for="ag-cfg">Arquivo/âmbito de configuração</label><input class="input mono" id="ag-cfg" placeholder="~/.config/…/settings.json" value="${esc(a.cfg)}">
          <div class="hint">${esc(a.note || "o Thero escreve provedor e modelo neste arquivo; o restante do conteúdo é preservado")}</div></div>
        <div class="field" style="margin-top:14px"><label for="ag-fmt">Formato</label>
          <select class="input" id="ag-fmt">${["json", "toml", "yml", "próprio", "—"].map((f) => `<option${f === a.format ? " selected" : ""}>${f}</option>`).join("")}</select></div>
        <div class="field" style="margin-top:14px"><label for="ag-prov">Provedor deste programa</label>
          <select class="input" id="ag-prov"><option value="">— sem provedor —</option>
            ${enabledProviders.map((p) => `<option value="${esc(p.preset)}"${p.preset === a.provider ? " selected" : ""}>${esc(p.label)}</option>`).join("")}</select>
          <div class="hint">o Zeus decide qual provedor usar em cada momento; aqui você declara só o padrão do programa.</div></div>
        <div class="field" style="margin-top:14px"><label for="ag-model">Modelo padrão</label><input class="input mono" id="ag-model" value="${esc(a.model)}"></div>
        <div class="switch-row" style="margin-top:16px"><div class="row-body"><span class="row-title">Receber as skills do Thero</span><span class="row-sub">mesma mecânica do <code>--publish</code>: SKILL.md ou comando .md no diretório nativo</span></div>
          <button class="switch" id="ag-skills" role="switch" aria-checked="${a.skills ? "true" : "false"}" aria-label="Receber skills"></button></div>
        <div class="chip-grid block" style="margin-top:20px">
          <button class="btn btn-primary" id="ag-save">Salvar</button>
          <button class="btn btn-ghost" id="ag-apply">${IC.send} Aplicar neste programa</button>
          ${state.agentDraft ? `<button class="btn btn-ghost" id="ag-cancel">Cancelar</button>`
            : `<button class="btn btn-ghost" id="ag-del">${IC.trash} Remover da lista</button>`}
        </div>
      </div>` : `<div class="banner info block">${IC.info}<div>Selecione um programa para ligá-lo a um provedor, definir o modelo e escolher se ele recebe as skills.</div></div>`}

      <div class="block"><div class="block-label">Adicionar um programa</div>
        <div class="search-row"><span>${IC.search}</span><input class="input mono" id="agent-q" placeholder="filtrar (codex, cline, aider, zed…)" value="${esc(state.agentQuery)}"></div>
        <div class="preset-grid block">${presets.map((x) => `<button class="preset${x.writes ? "" : " is-readonly"}" data-agent-preset="${x.id}">
            <span class="preset-name">${esc(x.name)}</span><span class="preset-meta">${esc(x.kind)}</span>
            <span class="preset-sub">${x.writes ? esc(x.cfg) : "só registra o modelo"}</span></button>`).join("")}</div>
        <div class="hint">Não está na lista? <b>Manual</b> aceita qualquer programa: você aponta o arquivo e o formato.</div>
      </div>
      <div class="block"><div class="chip-grid">
        <button class="btn btn-primary" id="ag-apply-all">Aplicar nos ${M.agents.filter((x) => x.status !== "em dia").length || M.agents.length} pendentes</button>
      </div></div>
    </div>`;
  };


  sec.models = () => {
    const ready = M.localModels.filter((m) => m.status === "pronto");
    const opt = (sel) => ready.map((m) => `<option${m.name === sel ? " selected" : ""}>${esc(m.name)}</option>`).join("");
    return `<div class="section section-wide">
      ${head("layers", "Modelos locais", "")}
      <p class="lede">O que roda na sua máquina e serve de alternativa (ou fallback) aos provedores de nuvem. Athena indexa em lote; Sentinel responde rápido — por isso cada um tem seu modelo.</p>
      <div class="block"><div class="block-label">Quem escolhe o provedor</div>
        <div class="chip-grid">
          <button class="chip${state.routingMode === "zeus" ? " is-on" : ""}" data-rmode="zeus">O Zeus decide, tarefa por tarefa</button>
          <button class="chip${state.routingMode === "fixo" ? " is-on" : ""}" data-rmode="fixo">Fixo por ferramenta (abaixo)</button>
        </div>
        <div class="hint">${state.routingMode === "zeus"
          ? "o Zeus escolhe entre os provedores ativos conforme a tarefa; os padrões abaixo viram o ponto de partida dele."
          : "cada ferramenta usa sempre o padrão definido abaixo — o Zeus não troca por conta própria."}</div>
      </div>
      <div class="block"><div class="block-label">Roteamento</div>
        <div class="field"><label for="rt-athena">Athena — indexação e resumo do índice</label><select class="input" id="rt-athena">${opt(state.routing.athena)}</select>
          <div class="hint">chamadas longas e em lote: contexto grande antes de velocidade.</div></div>
        <div class="field" style="margin-top:16px"><label for="rt-sentinel">Sentinel — leitura de estado e alertas</label><select class="input" id="rt-sentinel">${opt(state.routing.sentinel)}</select>
          <div class="hint">chamadas curtas e frequentes: latência antes de contexto.</div></div>
        <div class="field" style="margin-top:16px"><label for="rt-fallback">Fallback quando o local não responde</label>
          <select class="input" id="rt-fallback"><option${state.routing.fallback === "sem fallback" ? " selected" : ""}>sem fallback</option>
            ${M.providers.filter((x) => x.enabled).map((x) => `<option${x.label === state.routing.fallback ? " selected" : ""}>${esc(x.label)}</option>`).join("")}</select></div>
      </div>
      <div class="block"><div class="block-label">Inventário</div><div class="rows">
        ${M.localModels.map((m) => `<div class="row" style="cursor:default">
          <div class="row-body"><span class="row-title">${esc(m.name)}</span><span class="row-sub mono">${esc(m.provider)} · contexto ${esc(m.ctx)} · ${esc(m.size)}</span></div>
          <span class="pill ${m.status === "pronto" ? "ok" : m.status === "ausente" ? "err" : "warn"}">${esc(m.status)}</span>
          <span class="row-tag">${m.usedBy.length ? m.usedBy.join(", ") : "não usado"}</span></div>`).join("")}
      </div></div>
      <div class="block"><div class="chip-grid">
        <button class="btn btn-ghost" id="md-scan">${IC.search} Reescanear provedores</button>
        ${M.localModels.filter((m) => m.status === "ausente").map((m) => `<button class="btn btn-ghost" data-pull="${esc(m.name)}">${IC.download} Baixar ${esc(m.name)}</button>`).join("")}
      </div></div>
      <div class="banner warn">${IC.info}<div>Reescanear e baixar falam com o provedor local (ex.: API do Ollama). Na fase 2 isso sai do mock e vira chamada real pela ponte.</div></div>
    </div>`;
  };

  // ——— Skills: catálogo, busca, importação, origem ———
  sec.skills = () => {
    const upd = M.skills.filter((s) => s.update).length;
    const originTag = (s) => `<span class="origin${s.origin === "thero" ? " is-thero" : ""}">${s.origin === "thero" ? "Thero" : "Sua"}</span>`;
    return `<div class="section section-wide">
      ${head("skills", "Skills", "--skills-only")}
      <p class="lede">As skills que o Thero instala vêm do catálogo dele; as suas você adiciona por busca ou importação. As do Thero fazem parte da stack e <b>não</b> se desinstalam daqui — desativar é no projeto.</p>
      <div class="rows block">${M.skills.map((s) => `<div class="row${s.installed ? " is-on" : ""}" style="cursor:default">
        <span class="box"></span><div class="row-body"><span class="row-title">${esc(s.repo)}</span><span class="row-sub">${esc(s.desc)}</span></div>
        ${s.installed ? `<span class="row-tag">${s.update ? "atualizável" : "instalada"}</span>` : `<span class="row-tag">não instalada</span>`}
        ${originTag(s)}
        <span class="row-actions">
          ${s.installed ? "" : `<button class="btn btn-ghost btn-sm" data-add="${s.id}">${IC.plus} Adicionar</button>`}
          ${s.installed && s.origin === "user" ? `<button class="btn btn-ghost btn-sm" data-drop="${s.id}" title="remover a minha skill">${IC.trash}</button>` : ""}
          ${s.installed && s.origin === "thero" ? `<button class="btn btn-ghost btn-sm" disabled title="skill do Thero: não é removível pela interface">${IC.lock}</button>` : ""}
        </span></div>`).join("")}</div>
      ${upd ? `<div class="banner warn block">${IC.info}<div><b>${upd}</b> skill(s) com atualização disponível. Use <code>--update</code>.</div></div>` : ""}
      <div class="block"><div class="chip-grid">
        <button class="btn btn-primary" data-run="--skills-only" data-line="instalar o conjunto de skills">Instalar as do Thero</button>
        <button class="btn btn-ghost" data-run="--check" data-line="verificar atualizações de skills">Verificar (<code>--check</code>)</button>
        <button class="btn btn-ghost" data-run="--update" data-line="atualizar skills instaladas">Atualizar (<code>--update</code>)${upd ? ` · ${upd}` : ""}</button>
      </div></div>

      <div class="block card"><div class="block-label">Buscar mais skills</div>
        <div class="search-row"><span>${IC.search}</span><input class="input mono" id="skill-q" placeholder="termo: postgres, playwright, design tokens…" value="${esc(state.skillQuery)}"><button class="btn btn-ghost" id="skill-search">Buscar</button></div>
        <div class="hint">a busca vai ao catálogo de comunidade (mesmo canal do <code>npx skills</code>); o que você adicionar fica marcado como seu.</div>
        ${state.skillResults ? `<div class="rows block">${state.skillResults.map((r) => `<div class="row" style="cursor:default">
          <div class="row-body"><span class="row-title">${esc(r.repo)}</span><span class="row-sub">${esc(r.desc)}</span></div>
          <button class="btn btn-ghost btn-sm" data-add-found="${esc(r.id)}" data-repo="${esc(r.repo)}" data-desc="${esc(r.desc)}">${IC.plus} Adicionar</button></div>`).join("")}</div>` : ""}
      </div>

      <div class="block card"><div class="block-label">Importar manualmente</div>
        <div class="field"><label for="skill-import">Pasta da skill ou arquivo .zip já baixado</label>
          <div class="input-row"><input class="input mono" id="skill-import" placeholder="C:\\Users\\anthe\\Downloads\\minha-skill" value="${esc(state.importPath)}"><button class="btn btn-ghost" id="skill-import-btn">Importar</button></div>
          <div class="hint">para quando você baixou a skill por conta própria: ela entra na lista marcada como <b>Sua</b> e passa a ser removível.</div></div>
      </div>
    </div>`;
  };

  sec.claude = () => {
    const target = isLocal() ? "./CLAUDE.md" : "~/.claude/CLAUDE.md";
    return `<div class="section">
      ${head("doc", "CLAUDE.md", "--merge-only")}
      <p class="lede">Consolida o <b>Engineering Operating System</b> no arquivo alvo sem nunca apagar o seu conteúdo. Fluxo: backup com timestamp → merge via Claude → validação → substituição atômica.</p>
      <div class="mono-list block"><div class="mono-line"><span class="dot"></span>alvo: ${esc(target)}</div>
      <div class="mono-line"><span class="dot"></span>backup: <code>.backup_&lt;AAAAMMDD_HHMMSS&gt;</code> ao lado do original</div></div>
      <div class="block"><button class="btn btn-primary" data-run="--merge-only" data-line="mesclar o Engineering OS no CLAUDE.md">Mesclar CLAUDE.md</button></div>
      <div class="banner info">${IC.info}<div>Requer <b>Claude Code</b> autenticado${E.claude.ok && E.claude.authed ? " ✓" : " — não detectado"}. Rodar de novo é idempotente (não duplica o bloco).</div></div>
    </div>`;
  };

  sec.mcp = () => `<div class="section section-wide">
    ${head("plug", "Theroverse MCP", "--mcp")}
    <p class="lede">Um servidor JSON-RPC em stdio expõe Athena, Zeus e Thero como ferramentas a qualquer agente MCP. Bloqueia lendo stdin; não instala nada. O registro é o mesmo para os três clientes — muda só onde você cola.</p>
    <div class="block"><div class="block-label">Comando de registro</div>
      <div class="cmdline"><code id="mcpcmd">${esc(cmd("--mcp"))}</code><button class="btn btn-ghost btn-sm" data-copy="#mcpcmd">Copiar</button></div>
      <div class="mono-list block" style="margin-top:12px">
        <div class="mono-line"><span class="dot d-thero"></span>Claude Code&nbsp; <code>~/.claude.json → mcpServers</code></div>
        <div class="mono-line"><span class="dot d-athena"></span>OpenCode&nbsp; <code>bloco "mcp" da config</code></div>
        <div class="mono-line"><span class="dot d-zeus"></span>Qoder&nbsp; <code>config de servidores MCP</code></div>
      </div></div>
    <div class="block"><div class="block-label">${M.mcpTools.length} ferramentas expostas — definição única em mcp/capabilities.py</div>
      <div class="mono-list">${M.mcpTools.map((t) => `<div class="mono-line"><span class="dot d-${t.app}"></span><code>${esc(t.name)}</code>&nbsp; ${esc(t.desc)}</div>`).join("")}</div></div>
    <div class="block"><button class="btn btn-primary" data-run="--mcp" data-line="iniciar o servidor MCP (stdio)">Iniciar servidor</button></div>
    <div class="banner info">${IC.info}<div>stdout é exclusivo do JSON-RPC (banner vai para stderr) e o canal é UTF-8 forçado na partida — foi o que quebrou em Windows na primeira validação real.</div></div>
  </div>`;

  sec.publish = () => `<div class="section section-wide">
    ${head("send", "Publicar skills", "--publish")}
    <p class="lede">Escreve os arquivos nativos de cada agente (SKILL.md para Claude/Qoder, comando .md para OpenCode) com o caminho do CLI já resolvido — para uso onde MCP não está ativo. A saída mostra também a linha de <code>--mcp</code>.</p>
    <div class="block"><div class="block-label">Agentes-alvo (<code>--publish-agent</code>)</div>
      <div class="chip-grid">${M.publishAgents.map((a) => `<button class="chip${state.publishAgents.has(a.id) ? " is-on" : ""}" data-agent="${a.id}">${esc(a.name)}</button>`).join("")}
        <button class="chip${state.publishAgents.size === M.publishAgents.length ? " is-on" : ""}" data-agent-all>all</button></div></div>
    <div class="block field"><label for="pout">Pasta de saída (opcional) — <code>--publish-out DIR</code></label>
      <input class="input mono" id="pout" placeholder="vazio = diretório nativo de cada agente" value="${esc(state.publishOut)}"></div>
    <div class="block"><div class="block-label">Onde cai cada agente</div><div class="rows">
      ${M.publishAgents.map((a) => `<div class="row${state.publishAgents.has(a.id) ? " is-on" : ""}" style="cursor:default"><span class="box"></span>
        <div class="row-body"><span class="row-title">${esc(a.name)}</span><span class="row-sub mono">${esc(a.base)} · ${esc(a.kind)}</span></div>
        <span class="row-tag">${a.env ? "env " + esc(a.env) : "padrão"}</span></div>`).join("")}
    </div></div>
    <div class="block"><button class="btn btn-primary" data-default="1" data-line="publicar skills/comandos nos agentes">Publicar (--publish)</button></div>
    <div class="banner info">${IC.info}<div>Item sem script resolvível é <b>pulado com aviso</b> em vez de gravar caminho quebrado.</div></div>
  </div>`;

  // ——— Comandos: uma seção por flag/subcomando, com porquê e exemplos ———
  sec.commands = () => {
    return `<div class="section section-wide">
      ${head("cmd", "Comandos", "")}
      <p class="lede">Toda flag do <code>thero.py</code>, com o motivo de existir e como usar. O atalho <code>thero</code> é instalado automaticamente pelo fluxo completo e tem nome fixo — por isso não há aqui opção de instalar ou renomear comando.</p>
      <div class="block search-row"><span>${IC.search}</span><input class="input mono" id="cmd-q" placeholder="filtrar por comando, flag ou necessidade">
        <button class="btn btn-ghost" id="cmd-expand">Expandir tudo</button><button class="btn btn-ghost" id="cmd-collapse">Recolher tudo</button></div>
      <div class="doc-list block">
        ${M.commands.map((c) => `<details class="doc">
          <summary><span class="doc-name">${esc(c.name)}</span><code class="doc-flag">${esc(c.flag)}</code><span class="doc-kind">${esc(c.kind)}</span></summary>
          <div class="doc-body">
            <div class="doc-para"><div class="block-label">O que é</div><p>${esc(c.what)}</p></div>
            <div class="doc-para"><div class="block-label">Por que usar</div><p>${esc(c.why)}</p></div>
            <div class="doc-para"><div class="block-label">Como usar</div>
              ${c.how.map((h) => `<div class="cmdline" style="margin-top:8px"><code>${esc(h.cmd)}</code><button class="btn btn-ghost btn-sm" data-copyline="${esc(h.cmd)}">Copiar</button></div>
                <div class="hint">${esc(h.note)}</div>`).join("")}</div>
            <div class="doc-para"><div class="block-label">Requer</div><p class="doc-req">${esc(c.requires)}</p></div>
          </div></details>`).join("")}
        <div class="hint" id="cmd-empty" hidden>Nenhum comando casa com o filtro.</div>
      </div>
    </div>`;
  };

  // ————————————————— EXECUÇÃO (simulada; fase 2 = ponte) —————————————————
  const Bridge = {
    run(actionLine, cmdStr, onLine, onDone) {
      const ctx = { version: M.meta.version, scope: isLocal() ? "local" : "global", actionLine, cmd: cmdStr, config: M.meta.config };
      const lines = (kindOf(state.section) === "config" ? M.configLog : M.runLog).slice();
      let i = 0;
      (function step() {
        if (i >= lines.length) { setTimeout(() => onDone(true), 400); return; }
        const L = lines[i++];
        onLine({ type: L.t, text: L.s.replace(/\{(\w+)\}/g, (_, k) => (ctx[k] != null ? ctx[k] : "")), pct: Math.round((i / lines.length) * 100) });
        setTimeout(step, L.t === "act" ? 300 : 520);
      })();
    },
    // MOCK-PHASE2: ponte -> teste real de endpoint / npx skills search / pull local
    testProvider(p, cb) {
      if (!p.base) return cb({ ok: false, msg: "sem endpoint para testar: preencha o campo Endpoint" });
      cb({ ok: true, msg: "respondeu " + p.base + " · modelo " + (p.model || "não definido") });
    },
    // MOCK-PHASE2: ponte -> registro/autenticação (leitura de variável, sessão do produto, ping local)
    register(p, cb) {
      const kind = authKindOf(p);
      if (kind === "session") return cb({ ok: true, msg: "sessão confirmada no produto — provedor registrado" });
      if (kind === "local") return p.base ? cb({ ok: true, msg: "endpoint local alcance verificado — provedor registrado" })
        : cb({ ok: false, msg: "informe o endpoint local antes de registrar" });
      if (!p.authVar) return cb({ ok: false, msg: "defina o nome da variável que guarda a chave" });
      cb({ ok: true, msg: "provedor registrado · chave será lida de " + p.authVar + " a cada chamada" });
    },
    searchSkills(q, cb) { cb(M.skillResults.filter((r) => !q || (r.repo + " " + r.desc).toLowerCase().includes(q.toLowerCase()))); },
  };

  function openRun(actionLine, cmdStr) {
    const p = el("runpanel");
    const isCfg = kindOf(state.section) === "config";
    p.hidden = false;
    p.innerHTML = `<div class="sheet"><div class="sheet-top"><div class="sheet-brand"><img src="assets/thero-mark.png" alt=""><div><b>${isCfg ? "CONFIGURAÇÃO" : "EXECUÇÃO"}</b><small>${isCfg ? "gravação no config do Thero" : "saída do motor"}</small></div></div><button class="x" data-close>✕</button></div>
      <div class="sheet-pad">
        <div class="progress"><div class="bar"><div class="bar-fill" id="rbar"></div></div><div class="progress-meta"><span id="rstep">iniciando…</span><span id="rpct">0%</span></div></div>
        <div class="terminal"><div class="term-bar"><i></i><i></i><i></i><span>thero · ${isCfg ? "config" : "thero.py"}</span></div><div class="term-body" id="rterm"></div></div>
        <div class="sheet-foot"><span class="hint" id="rcmd"></span><span></span></div>
      </div></div>`;
    p.querySelector("[data-close]").addEventListener("click", () => (p.hidden = true));
    el("rcmd").textContent = cmdStr;
    const term = el("rterm"), bar = el("rbar"), pct = el("rpct"), step = el("rstep");
    term.innerHTML = '<span class="term-cursor"></span>';
    Bridge.run(actionLine, cmdStr, (L) => {
      const div = document.createElement("div"); div.className = "term-line";
      div.innerHTML = L.type === "act" ? `<span class="act">${esc(L.text)}</span>` : `<span class="${esc(L.type)}">${esc(L.text)}</span>`;
      term.insertBefore(div, term.querySelector(".term-cursor"));
      term.scrollTop = term.scrollHeight;
      bar.style.transform = "scaleX(" + (L.pct / 100) + ")"; pct.textContent = L.pct + "%"; step.textContent = L.text.trim().slice(0, 42);
    }, (ok) => {
      const c = term.querySelector(".term-cursor"); if (c) c.remove();
      const foot = p.querySelector(".sheet-foot");
      foot.innerHTML = `<div class="result-badge ${ok ? "ok" : "err"}" style="width:26px;height:26px;margin:0">${ok ? IC.check : IC.x}</div>
        <span style="color:var(--success);font-family:var(--font-mono);font-size:12px">exit 0 · ${isCfg ? "config gravada" : "processo concluído"}</span>
        <button class="btn btn-primary btn-sm" data-close2>Fechar</button>`;
      foot.querySelector("[data-close2]").addEventListener("click", () => (p.hidden = true));
    });
  }

  // ————————————————— ONBOARDING (1ª abertura) —————————————————
  function openOnboarding() {
    const p = el("onboarding"); let step = 0;
    const steps = ["preparar", "escopo", "provedor", "programas", "aplicar"];
    const titles = ["Bem-vindo ao Thero", "Onde configurar?", "Quem responde?", "Onde você trabalha?", "Aplicar e abrir"];
    const bodies = [preckStep, scopeStep, providerStep, programsStep, applyStep];
    let pick = "claude";
    const chosen = new Set(["claude"]); // programas-alvo marcados
    function draw() {
      p.hidden = false;
      p.innerHTML = `<div class="sheet"><div class="sheet-top"><div class="sheet-brand"><img src="assets/thero-mark.png" alt=""><div><b>THERO</b><small>primeira configuração</small></div></div>
        <div class="stepper">${steps.map((_, i) => `<span class="step-pip${i <= step ? " is-on" : ""}"></span>`).join("")}</div></div>
        <div class="sheet-pad"><h2>${titles[step]}</h2>${bodies[step]()}
          <div class="sheet-foot"><button class="btn btn-ghost" id="ob-back" ${step === 0 ? "disabled" : ""}>Voltar</button>
          ${step < steps.length - 1 ? `<button class="btn btn-primary" id="ob-next">Continuar</button>` : `<button class="btn btn-primary" id="ob-apply">Aplicar e abrir o Thero</button>`}</div></div></div>`;
      const back = p.querySelector("#ob-back"); if (back) back.addEventListener("click", () => { if (step > 0) { step--; draw(); } });
      const nx = p.querySelector("#ob-next");
      if (nx) nx.addEventListener("click", () => {
        if (step === 1) { const r = p.querySelector("[data-scope]:checked"); state.scope = r ? r.value : "global"; setScopeUI(); }
        if (step === 2) commitProviderPick();
        step++; draw();
      });
      p.querySelectorAll("[data-ob-pick]").forEach((b) => b.addEventListener("click", () => { pick = b.dataset.obPick; draw(); }));
      p.querySelectorAll("[data-ob-prog]").forEach((b) => b.addEventListener("click", () => {
        const k = b.dataset.obProg; chosen.has(k) ? chosen.delete(k) : chosen.add(k); b.classList.toggle("is-on");
        const n = p.querySelector("#ob-prog-count"); if (n) n.textContent = chosen.size ? chosen.size + " selecionado(s)" : "nenhum selecionado — dá para adicionar depois";
      }));
      const ap = p.querySelector("#ob-apply");
      if (ap) ap.addEventListener("click", () => {
        commitProviderPick();
        M.agents = [...chosen].map((k) => { const pre = M.agentPresets.find((x) => x.id === k); return { preset: pre.id, label: pre.name, cfg: pre.cfg, format: pre.format, provider: pick, model: (M.providerPresets.find((x) => x.id === pick) || {}).models[0] || "", enabled: true, status: "pendente", skills: !!pre.skills, origin: "thero" }; });
        state.agentSel = 0;
        p.hidden = true; E.firstRun = false; E.cliInstalled = true; render();
        openRun("aplicar a stack completa (1ª configuração)", cmd(""));
      });
    }
    function commitProviderPick() {
      const pre = M.providerPresets.find((x) => x.id === pick);
      if (pre && !M.providers.some((x) => x.preset === pre.id)) {
        M.providers.push({ preset: pre.id, label: pre.name, base: pre.base, authVar: "", transport: pre.transport, model: pre.models[0], enabled: true, origin: "user", roles: { athena: true, sentinel: true }, lastCheck: "definido no onboarding" });
      }
    }
    function preckStep() {
      const chk = (label, ok, note) => `<div class="row"><span class="pill ${ok ? "ok" : "err"}">${ok ? "ok" : "—"}</span><div class="row-body"><span class="row-title">${esc(label)}</span><span class="row-sub">${esc(note)}</span></div></div>`;
      return `<p class="lede">O app Portable confere os pré-requisitos da CLI antes de configurar qualquer coisa.</p><div class="preck block">
        ${chk("Python 3.10+", E.python.ok, "Python " + E.python.version)}${chk("Node.js / npx", E.node.ok, E.node.version)}${chk("Claude Code", E.claude.ok && E.claude.authed, "merge exige auth; skills funcionam sem")}
      </div>`;
    }
    function scopeStep() {
      return `<p class="lede">Global configura o usuário (<code>~/.claude</code>). Local escreve só na pasta do projeto (<code>--local</code>).</p>
      <div class="rows block">
        <label class="row${state.scope === "global" ? " is-on" : ""}"><input type="radio" name="sc" value="global" data-scope ${state.scope === "global" ? "checked" : ""} hidden><span class="box"></span><div class="row-body"><span class="row-title">Global (usuário)</span><span class="row-sub">skills em ~/.claude/skills · ~/.claude/CLAUDE.md</span></div></label>
        <label class="row${state.scope === "local" ? " is-on" : ""}"><input type="radio" name="sc" value="local" data-scope ${state.scope === "local" ? "checked" : ""} hidden><span class="box"></span><div class="row-body"><span class="row-title">Local (esta pasta)</span><span class="row-sub">./.claude/skills · ./CLAUDE.md</span></div></label>
      </div>`;
    }
    function providerStep() {
      const famous = M.providerPresets.filter((x) => x.famous);
      return `<p class="lede">Escolha quem responde quando Athena e Sentinel precisarem de IA. Dá para mudar depois — e adicionar quantos provedores quiser.</p>
      <div class="preset-grid block">${famous.map((x) => `<button class="preset${pick === x.id ? " is-on" : ""}" data-ob-pick="${x.id}">
        <span class="preset-name">${esc(x.name)}</span><span class="preset-meta">${esc(x.kind)}</span></button>`).join("")}</div>`;
    }
    function programsStep() {
      const list = M.agentPresets.filter((x) => x.famous || x.id === "manual");
      return `<p class="lede">Marque um ou mais programas onde o Thero deve aplicar provedor e modelo. Você pode mudar isso depois na tela <b>Programas alvo</b>.</p>
      <div class="preset-grid block">${list.map((x) => `<button class="preset${chosen.has(x.id) ? " is-on" : ""}" data-ob-prog="${x.id}">
        <span class="preset-name">${esc(x.name)}</span><span class="preset-meta">${esc(x.kind)}</span></button>`).join("")}</div>
      <div class="hint" id="ob-prog-count" style="margin-top:12px">${chosen.size ? chosen.size + " selecionado(s)" : "nenhum selecionado — dá para adicionar depois"}</div>`;
    }
    function applyStep() {
      const pre = M.providerPresets.find((x) => x.id === pick);
      const names = [...chosen].map((k) => (M.agentPresets.find((x) => x.id === k) || {}).name).filter(Boolean);
      return `<p class="lede">Isto roda o fluxo completo (<code>${esc(cmd(""))}</code>), grava o provedor escolhido e aplica nos programas marcados. Depois você cai direto na ferramenta.</p>
      <div class="mono-list block">
        <div class="mono-line"><span class="dot"></span>Skills — ${M.skills.filter((s) => s.installed).length} já instaladas, o resto será coberto</div>
        <div class="mono-line"><span class="dot"></span>CLAUDE.md — merge com backup</div>
        <div class="mono-line"><span class="dot"></span>Atalho — <code>thero</code> (nome fixo, instalado automaticamente)</div>
        <div class="mono-line"><span class="dot"></span>Provedor padrão — ${esc(pre ? pre.name : pick)} · ${esc(pre ? pre.models[0] : "")}</div>
        <div class="mono-line"><span class="dot"></span>Programas — ${names.length ? esc(names.join(", ")) : "nenhum (defina depois)"}</div></div>`;
    }
    draw();
  }

  // ————————————————— wiring —————————————————
  // lê a ficha aberta para dentro do objeto em edição (sem re-render: mantém o foco)
  function readForm() {
    const c = el("content");
    const p = draftOf();
    if (p) {
      const g = (id, key) => { const n = c.querySelector("#" + id); if (n) p[key] = n.value.trim(); };
      g("pv-label", "label"); g("pv-base", "base"); g("pv-var", "authVar"); g("pv-model", "model");
    }
    const a = draftAgent();
    if (a) { const ag = c.querySelector("#ag-label"); const ac = c.querySelector("#ag-cfg"); const af = c.querySelector("#ag-fmt"); const ap = c.querySelector("#ag-prov"); const am = c.querySelector("#ag-model");
      if (ag) a.label = ag.value.trim() || a.label; if (ac) a.cfg = ac.value.trim(); if (af) a.format = af.value; if (ap) a.provider = ap.value; if (am) a.model = am.value.trim(); }
  }

  function wire() {
    const c = el("content");
    c.querySelectorAll("[data-run]").forEach((b) => b.addEventListener("click", () => {
      openRun(b.dataset.line, ("python " + M.meta.entry + " " + b.dataset.run + (isLocal() ? " --local" : "")).replace(/\s+/g, " "));
    }));
    c.querySelectorAll("[data-default]").forEach((b) => b.addEventListener("click", () => openRun(b.dataset.line, defaultCmd())));
    c.querySelectorAll("[data-agent]").forEach((b) => b.addEventListener("click", () => { const k = b.dataset.agent; state.publishAgents.has(k) ? state.publishAgents.delete(k) : state.publishAgents.add(k); render(); }));
    const all = c.querySelector("[data-agent-all]"); if (all) all.addEventListener("click", () => { state.publishAgents = new Set(M.publishAgents.map((a) => a.id)); render(); });
    c.querySelectorAll("[data-copy]").forEach((b) => b.addEventListener("click", () => copy(b, c.querySelector(b.dataset.copy).textContent)));
    c.querySelectorAll("[data-copyline]").forEach((b) => b.addEventListener("click", () => copy(b, b.dataset.copyline)));

    // provedores
    c.querySelectorAll("[data-prov]").forEach((r) => r.addEventListener("click", () => { state.providerSel = +r.dataset.prov; state.providerDraft = null; render(); }));
    const saveRole = (b) => b && b.addEventListener("click", () => { const p = draftOf(); const k = b.dataset.role; p.roles[k] = !p.roles[k]; render(); });
    saveRole(c.querySelector('[data-role="athena"]')); saveRole(c.querySelector('[data-role="sentinel"]'));
    const pvOn = c.querySelector("#pv-on"); if (pvOn) pvOn.addEventListener("click", () => { const p = draftOf(); p.enabled = !p.enabled; render(); });
    const pvSave = c.querySelector("#pv-save");
    if (pvSave) pvSave.addEventListener("click", () => {
      readForm();
      if (state.providerDraft) { M.providers.push(state.providerDraft); state.providerSel = M.providers.length - 1; state.providerDraft = null; }
      else { currentProvider().lastCheck = "config gravada"; currentProvider().authState = currentProvider().authState === "aguardando chave" ? "aguardando chave" : (currentProvider().authState || "registrado"); }
      render();
      openRun("gravar provedor " + currentProvider().label, defaultCmd());
    });
    const pvAuth = c.querySelector("#pv-auth");
    if (pvAuth) pvAuth.addEventListener("click", () => {
      const p = draftOf(), out = c.querySelector("#pv-test-result");
      readForm();
      out.textContent = "registrando…";
      Bridge.register(p, (r) => {
        if (!r.ok) { out.innerHTML = `<span class="tag-err">${esc(r.msg)}</span>`; return; }
        p.lastCheck = r.msg; p.authState = authKindOf(p) === "session" ? "sessão ativa" : "registrado";
        if (state.providerDraft) { M.providers.push(p); state.providerDraft = null; state.providerSel = M.providers.length - 1; }
        render();
        openRun("registrar provedor " + p.label, cfg("providers." + p.label.toLowerCase().replace(/\s+/g, "-") + ".registered = true"));
      });
    });
    const pvTest = c.querySelector("#pv-test");
    if (pvTest) pvTest.addEventListener("click", () => {
      const out = c.querySelector("#pv-test-result"); out.textContent = "testando…";
      readForm();
      Bridge.testProvider(draftOf(), (r) => { out.innerHTML = `<span class="${r.ok ? "tag-ok" : "tag-err"}">${esc(r.msg)}</span>`; });
    });
    const pvDel = c.querySelector("#pv-del");
    if (pvDel) pvDel.addEventListener("click", () => {
      if (state.providerDraft) { state.providerDraft = null; render(); return; }
      M.providers.splice(state.providerSel, 1); state.providerSel = 0; render();
    });
    const pvCancel = c.querySelector("#pv-cancel"); if (pvCancel) pvCancel.addEventListener("click", () => { state.providerDraft = null; render(); });
    c.querySelectorAll("[data-preset]").forEach((b) => b.addEventListener("click", () => {
      const pre = M.providerPresets.find((x) => x.id === b.dataset.preset);
      state.providerDraft = { preset: pre.id, label: pre.name, base: pre.base, authVar: "", transport: pre.transport, authKind: pre.authKind, kind: pre.kind, model: pre.models[0], enabled: true, origin: "user", roles: { athena: false, sentinel: false }, lastCheck: "não testado" };
      render();
    }));
    const pq = c.querySelector("#preset-q");
    if (pq) pq.addEventListener("input", () => {
      const k = (state.presetQuery = pq.value).trim().toLowerCase();
      c.querySelectorAll(".preset").forEach((b) => { const pre = M.providerPresets.find((x) => x.id === b.dataset.preset); b.hidden = !k || (pre.name + " " + pre.kind + " " + pre.id).toLowerCase().includes(k); });
    });

    // ——— programas-alvo ———
    c.querySelectorAll("[data-agent-row]").forEach((r) => r.addEventListener("click", () => { state.agentSel = +r.dataset.agentRow; state.agentDraft = null; render(); }));
    const agSkills = c.querySelector("#ag-skills"); if (agSkills) agSkills.addEventListener("click", () => { const x = draftAgent(); x.skills = !x.skills; render(); });
    const agSave = c.querySelector("#ag-save");
    if (agSave) agSave.addEventListener("click", () => {
      const x = draftAgent();
      readForm();
      x.status = "pendente";
      if (state.agentDraft) { M.agents.push(x); state.agentSel = M.agents.length - 1; state.agentDraft = null; }
      render(); openRun("gravar programa " + x.label, defaultCmd());
    });
    const agApply = c.querySelector("#ag-apply");
    if (agApply) agApply.addEventListener("click", () => { const x = draftAgent(); x.status = "em dia"; render(); openRun("aplicar provedor/modelo em " + x.label, cfg("agents." + x.label.toLowerCase().replace(/\s+/g, "-") + " := " + (x.provider || "—") + "/" + (x.model || "—"))); });
    const agDel = c.querySelector("#ag-del"); if (agDel) agDel.addEventListener("click", () => { M.agents.splice(state.agentSel, 1); state.agentSel = 0; render(); });
    const agCancel = c.querySelector("#ag-cancel"); if (agCancel) agCancel.addEventListener("click", () => { state.agentDraft = null; render(); });
    const agAll = c.querySelector("#ag-apply-all"); if (agAll) agAll.addEventListener("click", () => { M.agents.forEach((x) => (x.status = "em dia")); render(); openRun("aplicar a configuração nos programas marcados", cfg("agents[ " + M.agents.map((x) => x.label).join(", ") + " ]")); });
    c.querySelectorAll("[data-agent-preset]").forEach((b) => b.addEventListener("click", () => {
      const pre = M.agentPresets.find((x) => x.id === b.dataset.agentPreset);
      state.agentDraft = { preset: pre.id, label: pre.name, cfg: pre.cfg, format: pre.format === "—" ? "—" : pre.format, provider: "", model: "", enabled: true, status: "novo", skills: !!pre.skills, origin: "user", note: pre.note };
      render();
    }));
    const aq = c.querySelector("#agent-q");
    if (aq) aq.addEventListener("input", () => {
      const k = (state.agentQuery = aq.value).trim().toLowerCase();
      c.querySelectorAll(".preset").forEach((b) => { const pre = M.agentPresets.find((x) => x.id === b.dataset.agentPreset); if (pre) b.hidden = !k || (pre.name + " " + pre.kind + " " + pre.cfg).toLowerCase().includes(k); });
    });

    // modelos locais
    c.querySelectorAll("[data-rmode]").forEach((b) => b.addEventListener("click", () => { state.routingMode = b.dataset.rmode; render(); }));
    bind(c, "rt-athena", "change", (v) => { state.routing.athena = v; syncCmd(); });
    bind(c, "rt-sentinel", "change", (v) => { state.routing.sentinel = v; syncCmd(); });
    bind(c, "rt-fallback", "change", (v) => { state.routing.fallback = v; syncCmd(); });
    const scan = c.querySelector("#md-scan"); if (scan) scan.addEventListener("click", () => openRun("reescanear modelos locais dos provedores", cfg("localModels[]")));
    c.querySelectorAll("[data-pull]").forEach((b) => b.addEventListener("click", () => openRun("baixar " + b.dataset.pull, cfg("localModels.pull = " + b.dataset.pull))));

    // skills
    bind(c, "skill-q", "input", (v) => { state.skillQuery = v; });
    const sSearch = c.querySelector("#skill-search");
    if (sSearch) sSearch.addEventListener("click", () => { Bridge.searchSkills(state.skillQuery, (r) => { state.skillResults = r; render(); }); });
    c.querySelectorAll("[data-add]").forEach((b) => b.addEventListener("click", (ev) => { ev.stopPropagation(); const s = M.skills.find((x) => x.id === b.dataset.add); s.installed = true; render(); openRun("adicionar skill " + s.repo, cmd("--skills-only")); }));
    c.querySelectorAll("[data-drop]").forEach((b) => b.addEventListener("click", (ev) => { ev.stopPropagation(); const s = M.skills.find((x) => x.id === b.dataset.drop); s.installed = false; s.origin === "user" && M.skills.splice(M.skills.indexOf(s), 1); render(); }));
    c.querySelectorAll("[data-add-found]").forEach((b) => b.addEventListener("click", () => {
      M.skills.push({ id: b.dataset.addFound, repo: b.dataset.repo, desc: b.dataset.desc, installed: true, update: false, origin: "user" });
      state.skillResults = null; state.skillQuery = ""; render();
    }));
    bind(c, "skill-import", "input", (v) => { state.importPath = v; });
    const imp = c.querySelector("#skill-import-btn");
    if (imp) imp.addEventListener("click", () => {
      const path = state.importPath.trim(); if (!path) return;
      const name = path.split(/[\\/]/).filter(Boolean).pop().replace(/\.zip$/i, "");
      M.skills.push({ id: "imported-" + name.toLowerCase(), repo: name, desc: "Importada manualmente de " + path, installed: true, update: false, origin: "user" });
      state.importPath = ""; render();
    });

    // comandos
    const cq = c.querySelector("#cmd-q");
    if (cq) cq.addEventListener("input", () => {
      const k = cq.value.trim().toLowerCase();
      const cards = [...c.querySelectorAll(".doc")];
      cards.forEach((d) => { const t = d.textContent.toLowerCase(); d.hidden = !!k && !t.includes(k); });
      c.querySelector("#cmd-empty").hidden = cards.some((d) => !d.hidden);
    });
    const ex = c.querySelector("#cmd-expand"); if (ex) ex.addEventListener("click", () => c.querySelectorAll(".doc").forEach((d) => (d.open = true)));
    const co = c.querySelector("#cmd-collapse"); if (co) co.addEventListener("click", () => c.querySelectorAll(".doc").forEach((d) => (d.open = false)));

    const sf = c.querySelector("#sim-first"); if (sf) sf.addEventListener("click", openOnboarding);
    c.querySelectorAll("[data-go]").forEach((b) => b.addEventListener("click", () => go(b.dataset.go)));
  }
  function copy(b, text) { navigator.clipboard && navigator.clipboard.writeText(text); const old = b.textContent; b.textContent = "Copiado"; setTimeout(() => (b.textContent = old), 1200); }
  function bind(c, id, ev, fn) { const n = c.querySelector("#" + id); if (n) n.addEventListener(ev, () => fn(n.value)); }

  // ————————————————— render —————————————————
  let focusAfter = null;
  function render() {
    const active = document.activeElement;
    if (active && active.id && /-(q|query)$/.test(active.id)) focusAfter = { id: active.id, pos: active.selectionStart };
    else if (active && active.id === "skill-import") focusAfter = { id: "skill-import", pos: active.selectionStart };
    else focusAfter = null;

    const s = SECTIONS.find((x) => x.id === state.section);
    el("titlebar-phase").textContent = "mock · " + s.label;
    el("content").innerHTML = (sec[state.section] || sec.status)();
    renderSidebar();
    wire();
    syncCmd();

    if (focusAfter) { const n = el("content").querySelector("#" + focusAfter.id); if (n) { n.focus(); try { n.setSelectionRange(focusAfter.pos, focusAfter.pos); } catch (e) {} } }
  }

  function setScopeUI() { el("scope-label").textContent = isLocal() ? "Local" : "Global"; el("scope-toggle").dataset.scope = state.scope; }

  el("scope-toggle").addEventListener("click", () => { state.scope = isLocal() ? "global" : "local"; E.scope = state.scope; setScopeUI(); render(); });
  el("btn-copy").addEventListener("click", () => copy(el("btn-copy"), defaultCmd()));
  el("btn-run").addEventListener("click", () => {
    const isCfg = kindOf(state.section) === "config";
    openRun(isCfg ? "gravar configuração de " + (state.section === "providers" ? "provedores" : "roteamento") : "executar " + state.section, defaultCmd());
  });
  el("btn-min").addEventListener("click", () => (el("titlebar-phase").textContent = "minimizado · mock"));
  el("btn-close").addEventListener("click", () => { if (confirm("Fechar o Thero (mock)?")) document.body.style.opacity = 0.3; });

  setScopeUI();
  render();
  if (E.firstRun || !E.cliInstalled) openOnboarding(); // primeira abertura => onboarding
})();
