"""Itens das licitações: preço estimado x preço homologado, e variação de preço do mesmo item.

Fonte: API do PNCP (itens e resultados de cada contratação).
"""
import re
import unicodedata
from collections import defaultdict

from . import config, pncp
from .rede import em_cache, get_json, salvar_json

BASE = "https://pncp.gov.br/api/pncp/v1"
MODALIDADES_COMPETITIVAS = ("Pregão", "Concorrência")


def _partes(numero_controle):
    cnpj, _, resto = numero_controle.split("-", 2)
    seq, ano = resto.split("/")
    return cnpj, ano, int(seq)


def _buscar_itens(numero_controle):
    cnpj, ano, seq = _partes(numero_controle)
    raiz = f"{BASE}/orgaos/{cnpj}/compras/{ano}/{seq}/itens"
    itens, pagina = [], 1
    while True:
        lote = get_json(raiz, {"pagina": pagina, "tamanhoPagina": 500}, timeout=60) or []
        itens += lote
        if len(lote) < 500:
            break
        pagina += 1
    saida = []
    for it in itens:
        resultados = []
        if it.get("temResultado"):
            for r in get_json(f"{raiz}/{it['numeroItem']}/resultados", timeout=60) or []:
                if r.get("dataCancelamento"):
                    continue
                resultados.append({
                    "ni": r.get("niFornecedor"), "tipo_pessoa": r.get("tipoPessoa"),
                    "nome": r.get("nomeRazaoSocialFornecedor"),
                    "unit": r.get("valorUnitarioHomologado"), "qtd": r.get("quantidadeHomologada"),
                    "total": r.get("valorTotalHomologado"), "data": r.get("dataResultado"),
                })
        saida.append({
            "n": it["numeroItem"], "desc": (it.get("descricao") or "").strip(),
            "tipo": it.get("materialOuServico"), "qtd": it.get("quantidade"),
            "un": (it.get("unidadeMedida") or "").strip(),
            "unit_est": it.get("valorUnitarioEstimado"), "total_est": it.get("valorTotal"),
            "sigiloso": bool(it.get("orcamentoSigiloso")),
            "crit": it.get("criterioJulgamentoNome") or "",
            "situacao": it.get("situacaoCompraItemNome"), "resultados": resultados,
        })
    return {"versao": None, "itens": saida}


def itens_da_compra(compra):
    """Itens de uma contratação. O cache é renovado quando a contratação é atualizada no PNCP."""
    numero = compra["numeroControlePNCP"]
    versao = compra.get("dataAtualizacaoGlobal") or compra.get("dataAtualizacao")
    arq = config.CACHE / "pncp" / "itens" / (numero.replace("/", "_") + ".json")
    dados = em_cache(arq, lambda: {**_buscar_itens(numero), "versao": versao})
    if dados.get("versao") != versao:
        dados = em_cache(arq, lambda: {**_buscar_itens(numero), "versao": versao}, renovar=True)
    if any("crit" not in it for it in dados["itens"]):
        cnpj, ano, seq = _partes(numero)
        crit, pagina = {}, 1
        while True:
            lote = get_json(f"{BASE}/orgaos/{cnpj}/compras/{ano}/{seq}/itens",
                            {"pagina": pagina, "tamanhoPagina": 500}, timeout=60) or []
            crit.update({x["numeroItem"]: x.get("criterioJulgamentoNome") or "" for x in lote})
            if len(lote) < 500:
                break
            pagina += 1
        for it in dados["itens"]:
            it["crit"] = crit.get(it["n"], "")
        salvar_json(arq, dados)
    return numero, dados["itens"]


def _chave_item(desc, un):
    s = unicodedata.normalize("NFD", f"{desc} | {un}")
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn").lower()
    return re.sub(r"[^a-z0-9|]+", " ", s).strip()


def _brl(v):
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def analisar(compras, itens_por_compra, unidade_da_compra):
    """Devolve (dados para o site, alertas)."""
    lista, resumo_compras, alertas = [], {}, []
    for numero, itens in itens_por_compra.items():
        c = compras[numero]
        ano = c.get("anoCompra")
        modalidade = c.get("modalidadeNome") or ""
        resumo_compras[numero] = {
            "objeto": (c.get("objetoCompra") or "").strip(), "modalidade": modalidade, "ano": ano,
            "unidade": unidade_da_compra(c), "link": pncp.link_compra(numero),
        }
        est_total = hom_total = 0.0
        acima = []
        for it in itens:
            for r in it["resultados"] or [None]:
                reg = {
                    "c": numero, "d": it["desc"], "u": it["un"], "q": (r or {}).get("qtd") or it["qtd"],
                    "e": None if it["sigiloso"] else it["unit_est"], "s": it["situacao"], "a": ano,
                }
                if r:
                    ni = r.get("ni") or ""
                    reg.update({
                        "h": r["unit"], "t": r["total"], "f": r["nome"], "dt": r["data"],
                        "ni": ni if r.get("tipo_pessoa") != "PF" else None,
                    })
                    if (not it["sigiloso"] and it["unit_est"] and r["unit"] and r["qtd"]
                            and it.get("crit", "").lower().startswith("menor pre")):
                        est_total += it["unit_est"] * r["qtd"]
                        hom_total += r["unit"] * r["qtd"]
                        if r["unit"] > it["unit_est"] * 1.01 and (r["total"] or 0) >= 10_000:
                            acima.append((it, r))
                lista.append(reg)

        if est_total > 0 and hom_total > 0:
            desconto = 1 - hom_total / est_total
            resumo_compras[numero].update({"estimado": round(est_total, 2), "homologado": round(hom_total, 2),
                                           "desconto": round(desconto, 4)})
            # Alerta: licitação competitiva que terminou praticamente no preço estimado
            if modalidade.startswith(MODALIDADES_COMPETITIVAS) and hom_total >= 200_000 and 0 <= desconto < 0.01:
                alertas.append({
                    "tipo": "sem_desconto", "gravidade": "media" if hom_total >= 1_000_000 else "baixa",
                    "titulo": "Licitação fechada praticamente no preço estimado",
                    "descricao": f"{modalidade} de {ano} ({resumo_compras[numero]['objeto'][:160]}): estimado "
                                 f"{_brl(est_total)}, homologado {_brl(hom_total)}, desconto de "
                                 + f"{desconto * 100:.2f}%".replace(".", ",") + ". Em disputa com concorrência real o preço "
                                 "costuma cair; desconto perto de zero pode indicar um único participante ou "
                                 "orçamento ajustado ao vencedor. Vale ler a ata da sessão.",
                    "valor": hom_total, "ano": ano, "compra": numero, "link": pncp.link_compra(numero),
                })
        # Alerta: item homologado acima do preço estimado
        if acima:
            excesso = sum((r["unit"] - it["unit_est"]) * r["qtd"] for it, r in acima)
            it, r = max(acima, key=lambda p: (p[1]["unit"] - p[0]["unit_est"]) * p[1]["qtd"])
            alertas.append({
                "tipo": "acima_estimado", "gravidade": "media",
                "titulo": "Item contratado acima do preço estimado",
                "descricao": f"Em {modalidade.lower()} de {ano}, {len(acima)} item(ns) foram homologados acima do "
                             f"valor estimado pela própria Prefeitura, somando {_brl(excesso)} a mais. Exemplo: "
                             f"\"{it['desc'][:120]}\", estimado {_brl(it['unit_est'])} e homologado {_brl(r['unit'])} "
                             f"por {it['un'] or 'unidade'}. A regra é desclassificar propostas acima do estimado.",
                "valor": excesso, "ano": ano, "compra": numero, "link": pncp.link_compra(numero),
            })

    # Mesmo item (descrição + unidade) homologado a preços muito diferentes em compras distintas do mesmo ano
    grupos = defaultdict(list)
    for reg in lista:
        if reg.get("h") and len(reg["d"]) >= 15:
            grupos[(_chave_item(reg["d"], reg["u"]), reg["a"])].append(reg)
    variacoes = []
    for (_, ano), regs in grupos.items():
        if len({r["c"] for r in regs}) < 2:
            continue
        menor, maior = min(regs, key=lambda r: r["h"]), max(regs, key=lambda r: r["h"])
        impacto = (maior["h"] - menor["h"]) * (maior["q"] or 0)
        if menor["c"] != maior["c"] and menor["h"] > 0 and maior["h"] / menor["h"] >= 1.5 and impacto >= 500:
            variacoes.append({
                "d": maior["d"], "u": maior["u"], "a": ano, "razao": round(maior["h"] / menor["h"], 2),
                "menor": {k: menor.get(k) for k in ("h", "f", "c", "dt", "q")},
                "maior": {k: maior.get(k) for k in ("h", "f", "c", "dt", "q")},
                "impacto": round(impacto, 2),
            })
    variacoes.sort(key=lambda v: -v["impacto"])

    lista.sort(key=lambda r: -(r.get("t") or 0))
    return {"itens": lista, "compras": resumo_compras, "variacoes": variacoes[:200]}, alertas
