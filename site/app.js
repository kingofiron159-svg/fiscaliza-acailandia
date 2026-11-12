"use strict";

const D = { contratos: [], fornecedores: [], alertas: [], orcamento: [], pessoal: [], receitas: [], financas: [], emendas: null, meta: {} };
const estado = { ano: "", aba: "inicio", graficos: {} };
const POR_PAGINA = 50;

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const brl = (v) => (v ?? 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
const brlCurto = (v) => {
  const a = Math.abs(v || 0);
  if (a >= 1e9) return "R$ " + (v / 1e9).toLocaleString("pt-BR", { maximumFractionDigits: 2 }) + " bi";
  if (a >= 1e6) return "R$ " + (v / 1e6).toLocaleString("pt-BR", { maximumFractionDigits: 1 }) + " mi";
  if (a >= 1e3) return "R$ " + (v / 1e3).toLocaleString("pt-BR", { maximumFractionDigits: 0 }) + " mil";
  return brl(v);
};
const data = (s) => (s ? s.slice(0, 10).split("-").reverse().join("/") : "—");
const doc = (ni) => (ni && ni.length === 14 ? ni.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, "$1.$2.$3/$4-$5") : ni || "—");
const norm = (s) => String(s ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const SEM_LICITACAO = new Set(["Dispensa", "Inexigibilidade"]);
const TIPOS_ALERTA = {
  sancao: "Empresa punida (CEIS/CNEP)", sem_desconto: "Licitação sem desconto", acima_estimado: "Acima do estimado", empresa_nova: "Empresa recém-aberta", situacao_cnpj: "CNPJ irregular", mei_acima_limite: "MEI acima do limite",
  capital_baixo: "Capital social baixo", fracionamento: "Possível fracionamento", direta_alta: "Contratação direta alta",
  concentracao: "Concentração", socio_comum: "Sócio em comum", lrf_pessoal: "Gasto com pessoal (LRF)", minimo_constitucional: "Mínimo constitucional", caixa_negativo: "Caixa negativo", receita_frustrada: "Receita abaixo do previsto",
};

const porAno = (lista) => (estado.ano ? lista.filter((x) => String(x.ano) === estado.ano) : lista);
const somar = (lista, f = (x) => x.valor) => lista.reduce((s, x) => s + (f(x) || 0), 0);
function agrupar(lista, chave) {
  const m = new Map();
  for (const x of lista) {
    const k = typeof chave === "function" ? chave(x) : x[chave];
    if (!m.has(k)) m.set(k, []);
    m.get(k).push(x);
  }
  return m;
}

// ---------- inicialização ----------
async function iniciar() {
  try {
    const r = await fetch("dados/dados.json", { cache: "no-cache" });
    if (r.status === 404) {
      $("#carregando").textContent = "Os dados ainda não foram gerados. Se a coleta (python coletar.py) está em andamento, aguarde: esta página tenta de novo sozinha a cada 30 segundos.";
      setTimeout(iniciar, 30000);
      return;
    }
    Object.assign(D, await r.json());
  } catch (e) {
    $("#carregando").textContent = "Não foi possível carregar os dados (" + e.message + "). Abra o site por um servidor web, por exemplo: python -m http.server 8765 --directory site";
    return;
  }
  D.fornPorNi = new Map(D.fornecedores.map((f) => [f.ni, f]));
  D.contrPorId = new Map(D.contratos.map((c) => [c.id, c]));
  D.alertasPorNi = agrupar(D.alertas.filter((a) => a.ni), "ni");
  for (const a of D.alertas) for (const id of a.contratos) {
    const c = D.contrPorId.get(id);
    if (c) (c.alertas ||= []).push(a);
  }

  const anos = [...new Set(D.contratos.map((c) => c.ano))].sort((a, b) => b - a);
  $("#ano").innerHTML = `<option value="">Todos (${D.meta.ano_inicial}–hoje)</option>` + anos.map((a) => `<option>${a}</option>`).join("");
  $("#ano").addEventListener("change", (e) => { estado.ano = e.target.value; renderizar(); });

  preencherSelect("#f-unidade", [...new Set(D.contratos.map((c) => c.unidade || c.orgao))].sort());
  preencherSelect("#f-modalidade", [...new Set(D.contratos.map((c) => c.modalidade))].sort());
  preencherSelect("#f-tipo", Object.keys(TIPOS_ALERTA).filter((t) => D.alertas.some((a) => a.tipo === t)), (t) => TIPOS_ALERTA[t]);

  for (const s of ["#busca-contratos", "#f-unidade", "#f-modalidade"]) $(s).addEventListener("input", () => { tabContr.pagina = 0; renderContratos(); });
  $("#busca-fornecedores").addEventListener("input", () => { tabForn.pagina = 0; renderFornecedores(); });
  $("#busca-emendas").addEventListener("input", () => { tabEmendas.pagina = 0; renderFederal(); });
  for (const s of ["#busca-itens", "#f-itens-res"]) $(s).addEventListener("input", () => { tabItens.pagina = 0; renderPrecos(); });
  for (const s of ["#f-gravidade", "#f-tipo"]) $(s).addEventListener("input", renderAlertas);
  $("#busca-glossario").addEventListener("input", renderGlossario);
  document.querySelectorAll("#tab-contratos th[data-ord]").forEach((th) => th.addEventListener("click", () => {
    const k = th.dataset.ord;
    tabContr.ord = tabContr.ord === k ? "-" + k : k;
    renderContratos();
  }));

  $("#abas").addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) irPara(b.dataset.aba); });
  document.addEventListener("click", tratarCliques);
  $("#modal .fechar").addEventListener("click", () => $("#modal").close());
  $("#modal").addEventListener("click", (e) => { if (e.target.id === "modal") $("#modal").close(); });

  $("#meta").textContent = `Dados atualizados em ${new Date(D.meta.gerado_em).toLocaleString("pt-BR")}. ` +
    `${D.contratos.length.toLocaleString("pt-BR")} contratos de ${D.meta.ano_inicial} em diante.` +
    (D.meta.sancoes_atualizadas_em?.ceis ? ` Cadastros de empresas punidas de ${data(D.meta.sancoes_atualizadas_em.ceis)}.` : "") +
    (D.meta.falhas_coleta ? ` Atenção: ${D.meta.falhas_coleta} consulta(s) falharam na última coleta.` : "");
  $("#carregando").remove();
  irPara(location.hash.slice(1) || "inicio");
}

function preencherSelect(sel, valores, rotulo = (v) => v) {
  $(sel).insertAdjacentHTML("beforeend", valores.map((v) => `<option value="${esc(v)}">${esc(rotulo(v))}</option>`).join(""));
}

function irPara(aba) {
  if (!document.getElementById("aba-" + aba)) aba = "inicio";
  estado.aba = aba;
  history.replaceState(null, "", "#" + aba);
  document.querySelectorAll(".aba").forEach((s) => (s.hidden = s.id !== "aba-" + aba));
  document.querySelectorAll("#abas button").forEach((b) => b.classList.toggle("ativa", b.dataset.aba === aba));
  renderizar();
}

function tratarCliques(e) {
  const t = e.target.closest("[data-contrato],[data-forn],[data-ir],[data-unidade],[data-termo]");
  if (!t) return;
  e.preventDefault();
  if (t.dataset.termo) return abrirTermo(t.dataset.termo);
  if (t.dataset.contrato) abrirContrato(t.dataset.contrato);
  else if (t.dataset.forn) abrirFornecedor(t.dataset.forn);
  else if (t.dataset.unidade) { $("#f-unidade").value = t.dataset.unidade; tabContr.pagina = 0; irPara("contratos"); }
  else if (t.dataset.ir) { $("#modal").close(); irPara(t.dataset.ir); }
}

function renderizar() {
  const alertasAno = porAno(D.alertas).filter((a) => a.gravidade === "alta");
  $("#badge-alertas").textContent = alertasAno.length || "";
  ({ inicio: renderInicio, alertas: renderAlertas, contratos: renderContratos, fornecedores: renderFornecedores, orcamento: renderOrcamento, federal: renderFederal, precos: renderPrecos, glossario: renderGlossario }[estado.aba] || (() => {}))();
}

// ---------- gráficos ----------
function grafico(id, cfg) {
  if (!window.Chart) return;
  estado.graficos[id]?.destroy();
  Chart.defaults.color = css("--suave");
  Chart.defaults.borderColor = css("--borda");
  Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
  estado.graficos[id] = new Chart(document.getElementById(id), cfg);
}

// ---------- Início ----------
function renderInicio() {
  const cs = porAno(D.contratos);
  const total = somar(cs);
  const direta = somar(cs.filter((c) => SEM_LICITACAO.has(c.modalidade)));
  const nForn = new Set(cs.map((c) => c.ni)).size;
  const altos = porAno(D.alertas).filter((a) => a.gravidade === "alta").length;
  $("#kpis").innerHTML = [
    [brlCurto(total), "contratado" + (estado.ano ? " em " + estado.ano : " no período")],
    [cs.length.toLocaleString("pt-BR"), "contratos publicados"],
    [nForn.toLocaleString("pt-BR"), "fornecedores diferentes"],
    [altos, `alertas de gravidade alta`, "alerta"],
  ].map(([v, r, cl]) => `<div class="kpi ${cl || ""}"><div class="v">${v}</div><div class="r">${r}</div></div>`).join("");

  const meses = agrupar(cs.filter((c) => c.assinatura), (c) => c.assinatura.slice(0, 7));
  const chaves = [...meses.keys()].sort();
  grafico("g-mes", {
    type: "bar",
    data: { labels: chaves.map((k) => k.split("-").reverse().join("/")), datasets: [{ data: chaves.map((k) => somar(meses.get(k))), backgroundColor: css("--primaria"), borderRadius: 3 }] },
    options: { maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => brl(c.raw) } } }, scales: { y: { ticks: { callback: (v) => brlCurto(v) } }, x: { grid: { display: false } } } },
  });

  const mods = [...agrupar(cs, "modalidade")].map(([k, v]) => [k, somar(v)]).sort((a, b) => b[1] - a[1]);
  const cores = mods.map(([k]) => (SEM_LICITACAO.has(k) ? (k === "Dispensa" ? css("--media") : css("--alta")) : k === "Não identificada" ? css("--baixa") : css("--primaria")));
  grafico("g-modalidade", {
    type: "doughnut",
    data: { labels: mods.map((m) => m[0]), datasets: [{ data: mods.map((m) => m[1]), backgroundColor: cores, borderColor: css("--cartao") }] },
    options: { maintainAspectRatio: false, plugins: { legend: { position: "right" }, tooltip: { callbacks: { label: (c) => `${c.label}: ${brl(c.raw)}` } } } },
  });
  $("#nota-direta").innerHTML = total ? `<strong>${((direta / total) * 100).toFixed(1).replace(".", ",")}%</strong> do valor foi contratado <strong>sem licitação</strong> (dispensa ou inexigibilidade). "Não identificada" são contratos cuja licitação de origem não está no PNCP.` : "";

  barras("#top-unidades", [...agrupar(cs, (c) => c.unidade || c.orgao)].map(([k, v]) => ({ nome: k, valor: somar(v), attr: `data-unidade="${esc(k)}"` })));
  barras("#top-fornecedores", [...agrupar(cs, "ni")].map(([k, v]) => ({ nome: v[0].fornecedor, valor: somar(v), attr: `data-forn="${esc(k)}"` })));
}

function barras(sel, itens, n = 10) {
  itens.sort((a, b) => b.valor - a.valor);
  const max = itens[0]?.valor || 1;
  $(sel).innerHTML = `<div class="barras">${itens.slice(0, n).map((i) => `
    <div class="barra clicavel" ${i.attr}><div class="linha"><span class="nome" title="${esc(i.nome)}">${esc(i.nome)}</span><span class="val">${brlCurto(i.valor)}</span></div>
    <div class="trilho"><div class="cheio" style="width:${(i.valor / max) * 100}%"></div></div></div>`).join("")}</div>` || "<p class='nota'>Sem dados.</p>";
}

// ---------- Alertas ----------
function renderAlertas() {
  const g = $("#f-gravidade").value, t = $("#f-tipo").value;
  const lista = porAno(D.alertas.map((a) => ({ ...a, ano: a.ano ?? anoDoAlerta(a) }))).filter((a) => (!g || a.gravidade === g) && (!t || a.tipo === t));
  $("#lista-alertas").innerHTML = lista.length ? lista.map((a) => `
    <article class="alerta-card ${a.gravidade}">
      <span class="etq ${a.gravidade}">${a.gravidade === "media" ? "média" : a.gravidade}</span>
      <span class="nota">${esc(TIPOS_ALERTA[a.tipo] || a.tipo)}${a.ano ? " · " + a.ano : ""}${a.valor ? " · " + brl(a.valor) : ""}</span>
      <h3>${esc(a.titulo)}</h3>
      <p>${esc(a.descricao)}</p>
      <div class="acoes">
        ${a.ni ? `<button class="link" data-forn="${esc(a.ni)}">Ver fornecedor</button>` : ""}
        ${a.link ? `<a href="${esc(a.link)}" target="_blank" rel="noopener">Ver licitação no PNCP ↗</a>` : ""}
        ${TERMO_DO_ALERTA[a.tipo] ? `<button class="link" data-termo="${TERMO_DO_ALERTA[a.tipo]}">Entenda o termo</button>` : ""}
        ${a.contratos.length === 1 ? `<button class="link" data-contrato="${esc(a.contratos[0])}">Ver contrato</button>` : a.contratos.length ? `<button class="link" data-forn="${esc(a.ni || D.contrPorId.get(a.contratos[0])?.ni || "")}">${a.contratos.length} contratos envolvidos</button>` : ""}
      </div>
    </article>`).join("") : `<div class="cartao"><p>Nenhum alerta com esses filtros.</p></div>`;
}
function anoDoAlerta(a) {
  const anos = new Set(a.contratos.map((id) => D.contrPorId.get(id)?.ano).filter(Boolean));
  return anos.size === 1 ? [...anos][0] : null;
}

// ---------- Contratos ----------
const tabContr = { pagina: 0, ord: "-assinatura" };
function contratosFiltrados() {
  const q = norm($("#busca-contratos").value), u = $("#f-unidade").value, m = $("#f-modalidade").value;
  const lista = porAno(D.contratos).filter((c) =>
    (!u || (c.unidade || c.orgao) === u) && (!m || c.modalidade === m) &&
    (!q || norm(`${c.objeto} ${c.fornecedor} ${c.ni} ${c.id}`).includes(q)));
  const desc = tabContr.ord.startsWith("-"), k = tabContr.ord.replace("-", "");
  lista.sort((a, b) => { const x = a[k] ?? "", y = b[k] ?? ""; return (x > y ? 1 : x < y ? -1 : 0) * (desc ? -1 : 1); });
  return lista;
}
function renderContratos() {
  const lista = contratosFiltrados();
  $("#resumo-contratos").textContent = `${lista.length.toLocaleString("pt-BR")} contratos · ${brl(somar(lista))}`;
  const pg = lista.slice(tabContr.pagina * POR_PAGINA, (tabContr.pagina + 1) * POR_PAGINA);
  $("#tab-contratos tbody").innerHTML = pg.map((c) => `
    <tr data-contrato="${esc(c.id)}">
      <td>${data(c.assinatura)}</td>
      <td>${esc(c.fornecedor)}${c.alertas ? ` <span class="etq ${c.alertas[0].gravidade}" title="Há alertas">!</span>` : ""}</td>
      <td><div class="obj">${esc(c.objeto)}</div></td>
      <td>${esc(c.unidade || c.orgao)}</td>
      <td>${esc(c.modalidade)}</td>
      <td class="num">${brl(c.valor)}</td>
    </tr>`).join("");
  paginacao("#pag-contratos", tabContr, lista.length, renderContratos);
}

function paginacao(sel, tab, total, render) {
  const n = Math.max(1, Math.ceil(total / POR_PAGINA));
  $(sel).innerHTML = `<button ${tab.pagina === 0 ? "disabled" : ""} data-p="-1">‹ Anterior</button><span>Página ${tab.pagina + 1} de ${n}</span><button ${tab.pagina >= n - 1 ? "disabled" : ""} data-p="1">Próxima ›</button>`;
  $(sel).onclick = (e) => { const b = e.target.closest("button[data-p]"); if (b) { tab.pagina += +b.dataset.p; render(); $(sel).parentElement.scrollIntoView({ behavior: "smooth" }); } };
}

// ---------- Fornecedores ----------
const tabForn = { pagina: 0 };
function renderFornecedores() {
  const q = norm($("#busca-fornecedores").value);
  const cs = porAno(D.contratos);
  const lista = [...agrupar(cs, "ni")].map(([ni, v]) => ({ f: D.fornPorNi.get(ni), total: somar(v), qtd: v.length }))
    .filter((x) => x.f && (!q || norm(`${x.f.nome} ${x.f.ni} ${x.f.cadastro?.nome_fantasia || ""}`).includes(q)))
    .sort((a, b) => b.total - a.total);
  const pg = lista.slice(tabForn.pagina * POR_PAGINA, (tabForn.pagina + 1) * POR_PAGINA);
  $("#tab-fornecedores tbody").innerHTML = pg.map(({ f, total, qtd }) => {
    const cad = f.cadastro || {};
    const nAl = (D.alertasPorNi.get(f.ni) || []).length;
    const sit = cad.situacao ? `<span class="etq ${cad.situacao === "ATIVA" ? "ok" : "alta"}">${esc(cad.situacao)}</span>` : "—";
    return `<tr data-forn="${esc(f.ni)}"><td>${esc(f.nome)}${f.sancoes ? ` <span class="etq alta" title="Consta em cadastro de empresas punidas">punida</span>` : ""}</td><td>${doc(f.ni)}</td><td>${data(cad.abertura)}</td><td>${sit}</td>
      <td class="num">${qtd}</td><td class="num">${brl(total)}</td><td class="num">${nAl ? `<span class="etq media">${nAl}</span>` : ""}</td></tr>`;
  }).join("");
  paginacao("#pag-fornecedores", tabForn, lista.length, renderFornecedores);
}

// ---------- Orçamento ----------
function renderFinancas() {
  const fs = [...(D.financas || [])].sort((a, b) => a.ano - b.ano);
  if (!fs.length) { $("#nota-financas").textContent = "Sem dados."; return; }
  const f = (estado.ano && fs.find((x) => String(x.ano) === estado.ano)) || [...fs].reverse().find((x) => x.fechado) || fs.at(-1);
  $("#nota-financas").innerHTML = `Indicadores de <strong>${f.ano}</strong>` + (f.fechado ? " (ano fechado)." : ` até o ${f.bimestre}º bimestre: <strong>ano em andamento</strong>, os percentuais mínimos só valem no fechamento.`) + " Fonte: RREO Anexo 14 e RGF Anexos 2 e 5, declarados pela própria Prefeitura ao Tesouro Nacional.";
  const pct = (v) => (v == null ? "—" : v.toLocaleString("pt-BR", { maximumFractionDigits: 2 }) + "%");
  const minimo = (v, min) => (v == null ? ["baixa", "sem dado"] : !f.fechado ? ["baixa", "parcial"] : v < min ? ["alta", "abaixo do mínimo"] : v < min + 0.5 ? ["media", "no limite"] : ["ok", "cumprido"]);
  const exec = f.receita_prevista ? (f.receita_realizada / f.receita_prevista) * 100 : null;
  const cartoes = [
    ["Educação", pct(f.educacao_pct), "mínimo de 25% dos impostos", minimo(f.educacao_pct, 25), "minimo_educacao"],
    ["Saúde", pct(f.saude_pct), "mínimo de 15% dos impostos", minimo(f.saude_pct, 15), "minimo_saude"],
    ["FUNDEB em salários", pct(f.fundeb_pct), "mínimo de 70% do fundo", minimo(f.fundeb_pct, 70), "fundeb"],
    ["Caixa livre", f.caixa_livre == null ? "—" : brlCurto(f.caixa_livre), "recursos não vinculados, após as obrigações", f.caixa_livre == null ? ["baixa", "só no fechamento"] : f.caixa_livre < 0 ? ["alta", "negativo"] : ["ok", "positivo"], "caixa"],
    ["Restos a pagar", f.rp_saldo == null ? "—" : brlCurto(f.rp_saldo), `ainda devidos, de ${brlCurto(f.rp_inscritos || 0)} herdados de anos anteriores`, ["baixa", "dívida com fornecedores"], "restos_a_pagar"],
    ["Dívida líquida", pct(f.divida_liquida_pct), "da receita corrente líquida (limite: 120%)", f.divida_liquida_pct == null ? ["baixa", "sem dado"] : f.divida_liquida_pct > 120 ? ["alta", "acima do limite"] : ["ok", "dentro do limite"], "divida"],
    ["Receita realizada", exec == null ? "—" : pct(exec), "do que o orçamento previa", exec == null || !f.fechado ? ["baixa", f.fechado ? "sem dado" : "parcial"] : exec < 90 ? ["media", "abaixo do previsto"] : ["ok", "conforme o previsto"], "dotacao"],
    ["Previdência própria", f.previdencia_resultado == null ? "—" : brlCurto(f.previdencia_resultado), "resultado do regime dos servidores no período", f.previdencia_resultado == null ? ["baixa", "sem dado"] : f.previdencia_resultado < 0 ? ["media", "déficit"] : ["ok", "superávit"], "previdencia"],
  ];
  $("#indicadores").innerHTML = cartoes.map(([nome, valor, legenda, [cls, rot], termo]) => `
    <div class="indicador"><div class="nome">${nome} <button class="ajuda" data-termo="${termo}" aria-label="O que é isso?">?</button></div>
      <div class="v">${valor}</div><div class="r">${legenda}</div><span class="etq ${cls}">${rot}</span></div>`).join("");
  const linhas = [["Educação (mín. 25%)", (x) => pct(x.educacao_pct)], ["Saúde (mín. 15%)", (x) => pct(x.saude_pct)], ["FUNDEB em salários (mín. 70%)", (x) => pct(x.fundeb_pct)],
    ["Caixa livre", (x) => (x.caixa_livre == null ? "—" : brlCurto(x.caixa_livre))], ["Restos a pagar (saldo)", (x) => (x.rp_saldo == null ? "—" : brlCurto(x.rp_saldo))],
    ["Dívida líquida / receita", (x) => pct(x.divida_liquida_pct)], ["Receita realizada / prevista", (x) => (x.receita_prevista ? pct((x.receita_realizada / x.receita_prevista) * 100) : "—")]];
  $("#tab-financas thead").innerHTML = `<tr><th>Evolução</th>${fs.map((x) => `<th class="num">${x.ano}${x.fechado ? "" : ` (${x.bimestre}º bim.)`}</th>`).join("")}</tr>`;
  $("#tab-financas tbody").innerHTML = linhas.map(([n, fn]) => `<tr><td>${n}</td>${fs.map((x) => `<td class="num">${fn(x)}</td>`).join("")}</tr>`).join("");
}

function renderOrcamento() {
  renderFinancas();
  const anoSel = estado.ano ? +estado.ano : Math.max(...D.orcamento.map((o) => o.ano));
  const o = D.orcamento.find((x) => x.ano === anoSel);
  if (o) {
    const f = o.funcoes.filter((x) => (x.dotacao || x.liquidado));
    $("#nota-orcamento").textContent = `${o.ano}, até o ${o.bimestre}º bimestre. Liquidado (despesa já reconhecida) ${brl(o.total.liquidado)} de uma dotação atualizada de ${brl(o.total.dotacao)}. Fonte: RREO, Anexo 2.`;
    grafico("g-funcoes", {
      type: "bar",
      data: {
        labels: f.map((x) => x.funcao),
        datasets: [
          { label: "Liquidado", data: f.map((x) => x.liquidado || 0), backgroundColor: css("--primaria"), borderRadius: 3 },
          { label: "Previsto (dotação atualizada)", data: f.map((x) => x.dotacao || 0), backgroundColor: css("--borda"), borderRadius: 3 },
        ],
      },
      options: { indexAxis: "y", maintainAspectRatio: false, plugins: { tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${brl(c.raw)}` } } }, scales: { x: { ticks: { callback: (v) => brlCurto(v) } }, y: { grid: { display: false } } } },
    });
  } else {
    $("#nota-orcamento").textContent = `Sem dados de orçamento para ${anoSel} no SICONFI.`;
    estado.graficos["g-funcoes"]?.destroy();
  }

  const p = [...D.pessoal].sort((a, b) => a.ano - b.ano);
  const linha = (v, cor, rot) => ({ label: rot, data: p.map(() => v), borderColor: cor, borderDash: [6, 4], pointRadius: 0, borderWidth: 1.5 });
  grafico("g-pessoal", {
    type: "line",
    data: {
      labels: p.map((x) => `${x.ano} (${x.periodo}º ${x.periodicidade === "Q" ? "quad." : "sem."})`),
      datasets: [
        { label: "Gasto com pessoal (% da RCL)", data: p.map((x) => x.despesa_pessoal_pct), borderColor: css("--primaria"), backgroundColor: css("--primaria"), borderWidth: 3, pointRadius: 5 },
        linha(54, css("--alta"), "Máximo 54%"), linha(51.3, css("--media"), "Prudencial 51,3%"), linha(48.6, css("--baixa"), "Alerta 48,6%"),
      ],
    },
    options: { maintainAspectRatio: false, plugins: { tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${c.raw?.toLocaleString("pt-BR")}%` } } }, scales: { y: { suggestedMin: 40, suggestedMax: 58, ticks: { callback: (v) => v + "%" } } } },
  });
}

// ---------- detalhes (modal) ----------
function abrirModal(html) { $("#modal-corpo").innerHTML = html; const m = $("#modal"); if (!m.open) m.showModal(); m.scrollTop = 0; }

function abrirContrato(id) {
  const c = D.contrPorId.get(id);
  if (!c) return;
  abrirModal(`
    <h2>${esc(c.objeto)}</h2>
    <dl class="dl">
      <dt>Fornecedor</dt><dd><button class="link" data-forn="${esc(c.ni)}">${esc(c.fornecedor)}</button> (${doc(c.ni)})</dd>
      <dt>Valor global <button class="ajuda" data-termo="contrato" aria-label="O que é isso?">?</button></dt><dd><strong>${brl(c.valor)}</strong></dd>
      <dt>Secretaria</dt><dd>${esc(c.unidade)}</dd>
      <dt>Como consta no PNCP</dt><dd>${esc(c.orgao)}${c.unidade_original ? " — " + esc(c.unidade_original) : ""}</dd>
      <dt>Assinatura</dt><dd>${data(c.assinatura)}</dd>
      <dt>Vigência até</dt><dd>${data(c.vigencia_fim)}</dd>
      <dt>Modalidade</dt><dd>${esc(c.modalidade)}${termoDaModalidade(c.modalidade) ? ` <button class="ajuda" data-termo="${termoDaModalidade(c.modalidade)}" aria-label="O que é isso?">?</button>` : ""}${c.amparo ? ` <span class="nota">(${esc(c.amparo)})</span>` : ""}</dd>
      <dt>Tipo</dt><dd>${esc(c.tipo || "—")} · ${esc(c.categoria || "—")}</dd>
      <dt>Nº de controle PNCP</dt><dd>${esc(c.id)}</dd>
      <dt>Documentos</dt><dd><a href="${esc(c.link)}" target="_blank" rel="noopener">Contrato no PNCP ↗</a>${c.link_compra ? ` · <a href="${esc(c.link_compra)}" target="_blank" rel="noopener">Licitação/compra de origem ↗</a>` : ""}</dd>
    </dl>
    ${c.alertas ? `<h3>Alertas</h3>${c.alertas.map((a) => `<p><span class="etq ${a.gravidade}">${a.gravidade}</span> <strong>${esc(a.titulo)}</strong> — ${esc(a.descricao)}</p>`).join("")}` : ""}`);
}

function abrirFornecedor(ni) {
  const f = D.fornPorNi.get(ni);
  if (!f) return;
  const cad = f.cadastro || {};
  const cs = D.contratos.filter((c) => c.ni === ni);
  const al = D.alertasPorNi.get(ni) || [];
  abrirModal(`
    <h2>${esc(f.nome)}</h2>
    <dl class="dl">
      <dt>${f.tipo === "PF" ? "CPF" : "CNPJ"}</dt><dd>${doc(ni)}</dd>
      ${cad.nome_fantasia ? `<dt>Nome fantasia</dt><dd>${esc(cad.nome_fantasia)}</dd>` : ""}
      <dt>Total contratado</dt><dd><strong>${brl(somar(cs))}</strong> em ${cs.length} contrato(s)</dd>
      ${f.cadastro ? `
      <dt>Abertura</dt><dd>${data(cad.abertura)}</dd>
      <dt>Situação na Receita <button class="ajuda" data-termo="situacao_cnpj" aria-label="O que é isso?">?</button></dt><dd>${esc(cad.situacao || "—")}${cad.data_situacao ? " desde " + data(cad.data_situacao) : ""}</dd>
      <dt>Atividade principal</dt><dd>${esc(cad.cnae || "—")}</dd>
      <dt>Porte / MEI</dt><dd>${esc(cad.porte || "—")}${cad.mei ? " · optante do MEI" : ""}</dd>
      <dt>Capital social <button class="ajuda" data-termo="capital_social" aria-label="O que é isso?">?</button></dt><dd>${cad.capital_social != null ? brl(cad.capital_social) : "—"}</dd>
      <dt>Sede</dt><dd>${esc(cad.municipio || "—")}/${esc(cad.uf || "")}</dd>
      <dt>Sócios</dt><dd>${cad.socios?.length ? cad.socios.map(esc).join("; ") : "—"}</dd>` : ""}
    </dl>
    ${al.length ? `<h3>Alertas</h3>${al.map((a) => `<p><span class="etq ${a.gravidade}">${a.gravidade}</span> <strong>${esc(a.titulo)}</strong> — ${esc(a.descricao)}</p>`).join("")}` : ""}
    ${f.sancoes ? `<h3>Punições registradas na CGU</h3>
    <div class="tabela-rolagem"><table class="tabela sem-clique"><thead><tr><th>Cadastro</th><th>Sanção</th><th>Período</th><th>Órgão que puniu</th><th>Abrangência</th></tr></thead><tbody>
    ${f.sancoes.map((s) => `<tr><td>${esc(s.cadastro)}</td><td>${esc(s.categoria)}</td><td>${data(s.inicio)} a ${s.fim ? data(s.fim) : "sem data final"}</td><td>${esc(s.orgao)}${s.uf ? "/" + esc(s.uf) : ""}</td><td>${esc(s.abrangencia || "—")}</td></tr>`).join("")}
    </tbody></table></div>
    <p class="nota">Fonte: <a href="https://portaldatransparencia.gov.br/sancoes/consulta?cadastro=1&cadastro=2&cpfCnpj=${esc(ni)}" target="_blank" rel="noopener">Portal da Transparência (CGU) ↗</a></p>` : ""}
    <h3>Contratos</h3>
    <div class="tabela-rolagem"><table class="tabela"><thead><tr><th>Data</th><th>Objeto</th><th>Modalidade</th><th class="num">Valor</th></tr></thead><tbody>
    ${cs.map((c) => `<tr data-contrato="${esc(c.id)}"><td>${data(c.assinatura)}</td><td><div class="obj">${esc(c.objeto)}</div></td><td>${esc(c.modalidade)}</td><td class="num">${brl(c.valor)}</td></tr>`).join("")}
    </tbody></table></div>`);
}

document.addEventListener("DOMContentLoaded", iniciar);

// ---------- Verbas e emendas ----------
const tabEmendas = { pagina: 0 };
const linkEmenda = (cod) => `https://portaldatransparencia.gov.br/emendas/detalhe?codigoEmenda=${encodeURIComponent(cod)}`;
function renderFederal() {
  // de onde vem a receita
  const rs = D.receitas || [];
  const anoSel = estado.ano ? +estado.ano : Math.max(0, ...rs.map((r) => r.ano));
  const r = rs.find((x) => x.ano === anoSel);
  if (r) {
    const propria = somar(r.fontes.filter((f) => f.origem === "propria"));
    $("#nota-receitas").innerHTML = `Receita corrente de <strong>${brl(r.total)}</strong> (12 meses até o ${r.bimestre}º bimestre de ${r.ano}). ` +
      `<strong>${(100 - (propria / r.total) * 100).toFixed(0)}%</strong> vem de repasses da União e do Estado; o restante é arrecadado pela própria Prefeitura. Fonte: RREO, Anexo 3.`;
    const cores = { propria: css("--primaria"), federal: css("--media"), estadual: css("--baixa") };
    grafico("g-receitas", {
      type: "bar",
      data: { labels: r.fontes.map((f) => f.nome), datasets: [{ data: r.fontes.map((f) => f.valor), backgroundColor: r.fontes.map((f) => cores[f.origem]), borderRadius: 3 }] },
      options: { indexAxis: "y", maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => `${brl(c.raw)} (${((c.raw / r.total) * 100).toFixed(1).replace(".", ",")}%)` } } }, scales: { x: { ticks: { callback: (v) => brlCurto(v) } }, y: { grid: { display: false } } } },
    });
  } else {
    $("#nota-receitas").textContent = "Sem dados de receita para o ano selecionado.";
    estado.graficos["g-receitas"]?.destroy();
  }

  const E = D.emendas;
  if (!E) { $("#kpis-emendas").innerHTML = "<p class='nota'>Dados de emendas indisponíveis nesta coleta.</p>"; return; }
  const publicos = E.recebidos.filter((x) => x.publico);
  const sel = porAno(publicos);
  const autores = [...agrupar(sel, "autor")].map(([nome, v]) => ({ nome, valor: somar(v), attr: "" }));
  $("#kpis-emendas").innerHTML = [
    [brlCurto(somar(sel)), "recebidos em emendas" + (estado.ano ? " em " + estado.ano : " desde 2016")],
    [new Set(sel.map((x) => x.emenda)).size, "emendas diferentes"],
    [autores.length, "autores (parlamentares, bancadas, comissões)"],
    [brlCurto(somar(porAno(E.convenios.map((c) => ({ ...c, ano: +(c.data || "").slice(0, 4) }))))), "em convênios de emendas"],
  ].map(([v, r]) => `<div class="kpi"><div class="v">${v}</div><div class="r">${r}</div></div>`).join("");

  const anos = [...agrupar(publicos, "ano")].sort((a, b) => a[0] - b[0]);
  grafico("g-emendas-ano", {
    type: "bar",
    data: { labels: anos.map((a) => a[0]), datasets: [{ data: anos.map((a) => somar(a[1])), backgroundColor: anos.map((a) => (!estado.ano || String(a[0]) === estado.ano ? css("--primaria") : css("--borda"))), borderRadius: 3 }] },
    options: { maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => brl(c.raw) } } }, scales: { y: { ticks: { callback: (v) => brlCurto(v) } }, x: { grid: { display: false } } } },
  });
  barras("#top-autores", autores, 12);
  document.querySelectorAll("#top-autores .barra").forEach((b) => b.classList.remove("clicavel"));

  const q = norm($("#busca-emendas").value);
  const lista = sel.filter((x) => !q || norm(`${x.autor} ${x.tipo} ${x.favorecido} ${x.funcao} ${x.acao} ${x.emenda}`).includes(q));
  $("#resumo-emendas").textContent = `${lista.length} repasses · ${brl(somar(lista))}`;
  $("#tab-emendas tbody").innerHTML = lista.slice(tabEmendas.pagina * POR_PAGINA, (tabEmendas.pagina + 1) * POR_PAGINA).map((x) => `
    <tr><td>${x.mes.split("-").reverse().join("/")}</td>
      <td>${esc(x.autor)}<br><a class="nota" href="${linkEmenda(x.emenda)}" target="_blank" rel="noopener">emenda ${esc(x.emenda)} ↗</a></td>
      <td>${esc(x.tipo.replace("Emenda Individual - ", "Individual: "))}</td>
      <td>${esc(x.favorecido)}</td>
      <td><strong>${esc(x.funcao || "—")}</strong>${x.acao ? `<div class="obj">${esc(x.acao)}</div>` : ""}</td>
      <td class="num">${brl(x.valor)}</td></tr>`).join("");
  paginacao("#pag-emendas", tabEmendas, lista.length, renderFederal);

  $("#tab-convenios tbody").innerHTML = E.convenios.map((c) => `
    <tr><td>${data(c.data)}</td><td>${esc(c.objeto)}<br><a class="nota" href="${linkEmenda(c.emenda)}" target="_blank" rel="noopener">convênio ${esc(c.numero)} · emenda ${esc(c.emenda)} ↗</a></td>
      <td>${esc(c.funcao)}</td><td>${esc(c.convenente)}</td><td class="num">${brl(c.valor)}</td></tr>`).join("") || `<tr><td colspan="5">Nenhum convênio encontrado.</td></tr>`;

  const privados = [...agrupar(porAno(E.recebidos.filter((x) => !x.publico)), "cnpj")].map(([cnpj, v]) => ({
    nome: `${v[0].favorecido} (${v[0].natureza})`, valor: somar(v), attr: D.fornPorNi.has(cnpj) ? `data-forn="${esc(cnpj)}"` : "" }));
  barras("#top-privados", privados, 15);
  document.querySelectorAll("#top-privados .barra:not([data-forn])").forEach((b) => b.classList.remove("clicavel"));
}

// ---------- Preços ----------
const tabItens = { pagina: 0 };
let P = null, carregandoPrecos = false;
async function renderPrecos() {
  if (!P) {
    if (carregandoPrecos) return;
    carregandoPrecos = true;
    try {
      P = await (await fetch("dados/itens.json", { cache: "no-cache" })).json();
      for (const i of P.itens) i._b = norm(`${i.d} ${i.f || ""}`);
    } catch (e) {
      $("#resumo-itens").textContent = "Não foi possível carregar os itens.";
      return;
    } finally { carregandoPrecos = false; }
  }
  const linkCompra = (id, txt) => { const c = P.compras[id]; return c?.link ? `<a href="${esc(c.link)}" target="_blank" rel="noopener">${txt} ↗</a>` : txt; };
  const q = norm($("#busca-itens").value).split(/\s+/).filter(Boolean), soRes = $("#f-itens-res").value;
  const lista = P.itens.filter((i) => (!estado.ano || String(i.a) === estado.ano) && (!soRes || i.h) && q.every((p) => i._b.includes(p)));
  $("#resumo-itens").textContent = `${lista.length.toLocaleString("pt-BR")} itens` + (soRes ? ` · ${brl(somar(lista, (i) => i.t))} homologados` : "");
  $("#tab-itens tbody").innerHTML = lista.slice(tabItens.pagina * POR_PAGINA, (tabItens.pagina + 1) * POR_PAGINA).map((i) => {
    const acima = i.h && i.e && i.h > i.e * 1.01;
    return `<tr class="sem-clique"><td><div class="obj" title="${esc(i.d)}">${esc(i.d)}</div><span class="nota">${linkCompra(i.c, esc(P.compras[i.c]?.modalidade || "licitação") + " " + i.a)}</span></td>
      <td>${esc(i.u || "—")}</td><td class="num">${(i.q ?? 0).toLocaleString("pt-BR")}</td>
      <td class="num">${i.e ? brl(i.e) : "—"}</td>
      <td class="num">${i.h ? brl(i.h) : `<span class="nota">${esc(i.s || "—")}</span>`}${acima ? ` <span class="etq media" title="Acima do estimado">↑</span>` : ""}</td>
      <td class="num">${i.t ? brl(i.t) : "—"}</td>
      <td>${i.ni && D.fornPorNi.has(i.ni) ? `<button class="link" data-forn="${esc(i.ni)}">${esc(i.f)}</button>` : esc(i.f || "—")}</td>
      <td>${data(i.dt)}</td></tr>`;
  }).join("") || `<tr><td colspan="8">Nenhum item encontrado.</td></tr>`;
  paginacao("#pag-itens", tabItens, lista.length, renderPrecos);

  const desc = Object.entries(P.compras).filter(([, c]) => c.desconto != null && c.homologado >= 100000 && /^(Pregão|Concorrência)/.test(c.modalidade) && (!estado.ano || String(c.ano) === estado.ano))
    .sort((a, b) => a[1].desconto - b[1].desconto);
  if (desc.length) $("#nota-desconto").innerHTML = `Para comparar: o desconto típico (mediana) nas ${desc.length} licitações deste recorte foi de <strong>${(desc[Math.floor(desc.length / 2)][1].desconto * 100).toFixed(0)}%</strong>.`;
  desc.length = Math.min(desc.length, 30);
  $("#tab-descontos tbody").innerHTML = desc.map(([id, c]) => `
    <tr><td><div class="obj">${esc(c.objeto)}</div><span class="nota">${linkCompra(id, esc(c.modalidade) + " " + c.ano)}</span></td><td>${esc(c.unidade)}</td>
      <td class="num">${brl(c.estimado)}</td><td class="num">${brl(c.homologado)}</td>
      <td class="num"><span class="etq ${c.desconto < 0 ? "alta" : c.desconto < 0.01 ? "media" : c.desconto < 0.05 ? "baixa" : "ok"}">${(c.desconto * 100).toFixed(1).replace(".", ",")}%</span></td></tr>`).join("") || `<tr><td colspan="5">Sem dados.</td></tr>`;

  const vs = P.variacoes.filter((v) => !estado.ano || String(v.a) === estado.ano).slice(0, 50);
  const lado = (x) => `${brl(x.h)}<br><span class="nota">${esc(x.f || "")} · ${linkCompra(x.c, "licitação")}</span>`;
  $("#tab-variacoes tbody").innerHTML = vs.map((v) => `
    <tr><td><div class="obj" title="${esc(v.d)}">${esc(v.d)}</div><span class="nota">por ${esc(v.u || "unidade")}</span></td><td>${v.a}</td>
      <td class="num">${lado(v.menor)}</td><td class="num">${lado(v.maior)}</td>
      <td class="num"><span class="etq ${v.razao >= 3 ? "alta" : "media"}">${v.razao.toLocaleString("pt-BR")}×</span></td>
      <td class="num">${brl(v.impacto)}</td></tr>`).join("") || `<tr><td colspan="6">Nenhuma variação relevante encontrada.</td></tr>`;
}

// ---------- Glossário ----------
const TERMO_DO_ALERTA = {
  sancao: "ceis", fracionamento: "fracionamento", direta_alta: "dispensa", mei_acima_limite: "mei", capital_baixo: "capital_social",
  situacao_cnpj: "situacao_cnpj", socio_comum: "socios", lrf_pessoal: "lrf", sem_desconto: "estimado", acima_estimado: "estimado",
};
function termoDaModalidade(m) {
  const n = norm(m);
  return n.startsWith("pregao") ? "pregao" : n.startsWith("concorrencia") ? "concorrencia" : n.startsWith("dispensa") ? "dispensa"
    : n.startsWith("inexigibilidade") ? "inexigibilidade" : n.startsWith("credenciamento") ? "credenciamento" : "";
}
function abrirTermo(chave) {
  const t = window.GLOSSARIO?.[chave] ?? (typeof GLOSSARIO !== "undefined" ? GLOSSARIO[chave] : null);
  if (!t) return;
  abrirModal(`<p class="nota">${esc(t[1])}</p><h2>${esc(t[0])}</h2><p>${esc(t[2])}</p>
    ${t[3] ? `<p class="nota">Base legal: ${esc(t[3])}</p>` : ""}
    <p><button class="link" data-ir="glossario">Ver o glossário completo</button></p>`);
}
function renderGlossario() {
  if (typeof GLOSSARIO === "undefined") return;
  const q = norm($("#busca-glossario").value);
  const grupos = agrupar(Object.values(GLOSSARIO).filter((t) => !q || norm(t[0] + " " + t[2]).includes(q)), (t) => t[1]);
  $("#lista-glossario").innerHTML = [...grupos].map(([g, ts]) => `<div class="cartao"><h2>${esc(g)}</h2><dl class="glossario">
    ${ts.sort((a, b) => a[0].localeCompare(b[0], "pt-BR")).map((t) => `<dt>${esc(t[0])}</dt><dd>${esc(t[2])}${t[3] ? ` <span class="nota">(${esc(t[3])})</span>` : ""}</dd>`).join("")}
  </dl></div>`).join("") || `<div class="cartao"><p>Nenhum termo encontrado.</p></div>`;
}

Object.assign(TERMO_DO_ALERTA, { minimo_constitucional: "minimo_educacao", caixa_negativo: "caixa", receita_frustrada: "dotacao" });
