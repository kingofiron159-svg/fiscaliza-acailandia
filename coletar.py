"""Coleta os dados públicos e gera site/dados/dados.json.

Uso:  python coletar.py
A primeira execução demora (a API do PNCP é lenta). As seguintes reaproveitam o cache
e só baixam de novo os últimos meses.
"""
import datetime as dt
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from fiscaliza import alertas, cnpj, config, federal, pncp, precos, sancoes, siconfi, unidades
from fiscaliza.rede import salvar_json


def log(msg):
    print(f"[{dt.datetime.now():%H:%M:%S}] {msg}", flush=True)


def paralelo(func, tarefas, workers=4, rotulo=""):
    resultados, erros = [], 0
    with ThreadPoolExecutor(workers) as ex:
        futuros = [ex.submit(func, *t) for t in tarefas]
        for i, f in enumerate(futuros, 1):
            try:
                resultados.append(f.result())
            except Exception as e:  # registra e segue: um mês com falha não derruba a coleta
                erros += 1
                log(f"  ERRO {rotulo} {tarefas[i - 1]}: {e}")
            if i % 10 == 0 or i == len(futuros):
                log(f"  {rotulo}: {i}/{len(futuros)}")
    return resultados, erros


def mascarar_cpf(ni):
    return f"***.{ni[3:6]}.{ni[6:9]}-**" if len(ni) == 11 else ni


def main():
    inicio = time.time()
    hoje = dt.date.today()
    anos = list(range(config.ANO_INICIAL, hoje.year + 1))

    log("1/8 Licitações e contratações diretas (PNCP)")
    tarefas = [(a, m) for a in anos for m in pncp.MODALIDADES]
    blocos, erros_compras = paralelo(pncp.contratacoes_ano, tarefas, rotulo="contratações")
    compras = {}
    for bloco in blocos:
        for c in bloco or []:
            if c["orgaoEntidade"].get("esferaId") == "M":  # só órgãos municipais
                compras[c["numeroControlePNCP"]] = c
    orgaos = {config.CNPJ_PREFEITURA: "MUNICIPIO DE " + config.CIDADE.upper()}
    for c in compras.values():
        orgaos[c["orgaoEntidade"]["cnpj"]] = c["orgaoEntidade"]["razaoSocial"]
    log(f"  {len(compras)} contratações; órgãos: {', '.join(orgaos.values())}")

    log("2/8 Contratos (PNCP, mês a mês)")
    meses = [(a, m) for a in anos for m in range(1, 13) if dt.date(a, m, 1) <= hoje]
    tarefas = [(o, a, m) for o in orgaos for a, m in meses]
    blocos, erros_contratos = paralelo(pncp.contratos_mes, tarefas, rotulo="contratos")
    brutos = {}
    for bloco in blocos:
        for c in bloco or []:
            atual = brutos.get(c["numeroControlePNCP"])
            if not atual or c["dataAtualizacao"] > atual["dataAtualizacao"]:
                brutos[c["numeroControlePNCP"]] = c

    contratos = []
    for c in brutos.values():
        if c.get("receita"):  # contratos de receita (o município recebendo) ficam de fora
            continue
        compra = compras.get(c.get("numeroControlePncpCompra") or "", {})
        assinatura = c.get("dataAssinatura") or c.get("dataPublicacaoPncp", "")[:10]
        ni = c.get("niFornecedor") or ""
        contratos.append({
            "id": c["numeroControlePNCP"],
            "orgao": c["orgaoEntidade"]["razaoSocial"],
            "unidade": unidades.unificar((c.get("unidadeOrgao") or {}).get("nomeUnidade"), c["orgaoEntidade"]["razaoSocial"]),
            "unidade_original": ((c.get("unidadeOrgao") or {}).get("nomeUnidade") or "").strip() or None,
            "fornecedor": c.get("nomeRazaoSocialFornecedor"),
            "ni": ni if c.get("tipoPessoa") != "PF" else mascarar_cpf(ni),
            "tipo_pessoa": c.get("tipoPessoa"),
            "objeto": (c.get("objetoContrato") or "").strip(),
            "valor": float(c.get("valorGlobal") or c.get("valorInicial") or 0),
            "assinatura": assinatura,
            "vigencia_fim": c.get("dataVigenciaFim"),
            "ano": int(assinatura[:4]) if assinatura else c.get("anoContrato"),
            "tipo": (c.get("tipoContrato") or {}).get("nome"),
            "categoria": (c.get("categoriaProcesso") or {}).get("nome"),
            "modalidade": compra.get("modalidadeNome") or "Não identificada",
            "amparo": (compra.get("amparoLegal") or {}).get("nome"),
            "compra": c.get("numeroControlePncpCompra"),
            "link": pncp.link_contrato(c),
            "link_compra": pncp.link_compra(c["numeroControlePncpCompra"]) if c.get("numeroControlePncpCompra") else None,
        })
    contratos = [c for c in contratos if c["ano"] and c["ano"] >= config.ANO_INICIAL]
    contratos.sort(key=lambda c: c["assinatura"], reverse=True)
    log(f"  {len(contratos)} contratos")

    log("3/8 Cadastro dos fornecedores (Receita Federal)")
    fornecedores = {}
    for c in contratos:
        f = fornecedores.setdefault(c["ni"], {"ni": c["ni"], "nome": c["fornecedor"], "tipo": c["tipo_pessoa"],
                                              "total": 0.0, "qtd": 0})
        f["total"] += c["valor"]
        f["qtd"] += 1
    pjs = [(ni,) for ni, f in fornecedores.items() if f["tipo"] == "PJ" and len(ni) == 14]
    cadastros, _ = paralelo(cnpj.consultar, pjs, workers=3, rotulo="CNPJs")
    for cad in cadastros:
        if cad and cad.get("cnpj") in fornecedores and not cad.get("erro"):
            fornecedores[cad["cnpj"]]["cadastro"] = cad

    log("4/8 Empresas punidas (CEIS e CNEP, CGU)")
    datas_sancoes, erros_sancoes = {}, 0
    try:
        indice, datas_sancoes = sancoes.por_raiz_cnpj()
        for ni, f in fornecedores.items():
            if f["tipo"] == "PJ" and len(ni) == 14 and ni[:8] in indice:
                f["sancoes"] = indice[ni[:8]]
        log(f"  {sum(1 for f in fornecedores.values() if f.get('sancoes'))} fornecedores com sanção registrada")
    except RuntimeError as e:
        erros_sancoes = 1
        log(f"  ERRO: {e}")

    log("5/8 Emendas parlamentares (CGU)")
    emendas, erros_emendas = None, 0
    try:
        emendas = federal.emendas()
        log(f"  {len(emendas['recebidos'])} repasses a favorecidos da cidade; {len(emendas['convenios'])} convênios")
    except Exception as e:  # arquivo grande: falha de rede não deve derrubar o resto
        erros_emendas = 1
        log(f"  ERRO: {e}")

    log("6/8 Orçamento, receitas e despesa com pessoal (SICONFI)")
    orcamento = [o for o in (siconfi.despesas_por_funcao(a) for a in anos) if o]
    pessoal = [p for p in (siconfi.despesa_pessoal(a) for a in anos) if p]
    receitas = [r for r in (siconfi.receitas(a) for a in anos) if r]
    financas = [f for f in (siconfi.saude_financeira(a) for a in anos) if f]

    log("7/8 Itens e preços das licitações (PNCP)")
    blocos, erros_itens = paralelo(precos.itens_da_compra, [(c,) for c in compras.values()], workers=8, rotulo="itens")
    dados_precos, alertas_precos = precos.analisar(
        compras, dict(blocos),
        lambda c: unidades.unificar((c.get("unidadeOrgao") or {}).get("nomeUnidade"), c["orgaoEntidade"]["razaoSocial"]))
    por_compra = {}
    for c in contratos:
        if c.get("compra"):
            por_compra.setdefault(c["compra"], []).append(c["id"])
    for a in alertas_precos:
        a.update({"ni": None, "fornecedor": None, "contratos": por_compra.get(a["compra"], [])})
    salvar_json(config.SAIDA / "itens.json", dados_precos, compacto=True)
    log(f"  {len(dados_precos['itens'])} itens; {len(dados_precos['variacoes'])} variações de preço")

    log("8/8 Alertas")
    lista_alertas = alertas.gerar(contratos, fornecedores, pessoal, extras=alertas_precos, financas=financas)
    log(f"  {len(lista_alertas)} alertas")

    salvar_json(config.SAIDA / "dados.json", {
        "meta": {
            "cidade": config.CIDADE, "uf": config.UF, "ibge": config.CODIGO_IBGE,
            "gerado_em": dt.datetime.now().isoformat(timespec="minutes"),
            "ano_inicial": config.ANO_INICIAL,
            "falhas_coleta": erros_compras + erros_contratos + erros_sancoes + erros_emendas + erros_itens,
            "sancoes_atualizadas_em": datas_sancoes,
        },
        "contratos": contratos,
        "fornecedores": sorted(fornecedores.values(), key=lambda f: -f["total"]),
        "alertas": lista_alertas,
        "orcamento": orcamento,
        "pessoal": pessoal,
        "receitas": receitas,
        "financas": financas,
        "emendas": emendas,
    }, compacto=True)
    log(f"Pronto em {time.time() - inicio:.0f}s -> {config.SAIDA / 'dados.json'}")
    if erros_compras + erros_contratos + erros_sancoes + erros_emendas + erros_itens:
        log("Houve falhas em algumas consultas; rode de novo para completar.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
