"""SICONFI / Tesouro Nacional - relatórios fiscais (RREO e RGF). https://apidatalake.tesouro.gov.br/docs/siconfi/"""
import datetime as dt

from . import config
from .rede import em_cache, get_json

BASE = "https://apidatalake.tesouro.gov.br/ords/siconfi/tt"

# As 28 funções de governo (Portaria MOG 42/1999). O RREO mistura funções e subfunções na mesma lista.
FUNCOES = {
    "Legislativa", "Judiciária", "Essencial à Justiça", "Administração", "Defesa Nacional",
    "Segurança Pública", "Relações Exteriores", "Assistência Social", "Previdência Social", "Saúde",
    "Trabalho", "Educação", "Cultura", "Direitos da Cidadania", "Urbanismo", "Habitação", "Saneamento",
    "Gestão Ambiental", "Ciência e Tecnologia", "Agricultura", "Organização Agrária", "Indústria",
    "Comércio e Serviços", "Comunicações", "Energia", "Transporte", "Desporto e Lazer", "Encargos Especiais",
}


def _renovar(ano):
    return ano >= dt.date.today().year - 1


def _rreo_anexo2(ano):
    for periodo in range(6, 0, -1):
        itens = (get_json(f"{BASE}/rreo", {
            "an_exercicio": ano, "nr_periodo": periodo, "co_tipo_demonstrativo": "RREO",
            "no_anexo": "RREO-Anexo 02", "id_ente": config.CODIGO_IBGE,
        }) or {}).get("items", [])
        if itens:
            return {"periodo": periodo, "itens": itens}
    return None


def despesas_por_funcao(ano):
    bruto = em_cache(config.CACHE / "siconfi" / f"rreo2_{ano}.json", lambda: _rreo_anexo2(ano), renovar=_renovar(ano))
    if not bruto:
        return None
    funcoes, total = {}, {}
    for x in bruto["itens"]:
        if not x["rotulo"].startswith("Total das Despesas Exceto"):
            continue
        col = x["coluna"]
        if col.startswith("DOTAÇÃO ATUALIZADA"):
            campo = "dotacao"
        elif col.startswith("DESPESAS EMPENHADAS ATÉ"):
            campo = "empenhado"
        elif col.startswith("DESPESAS LIQUIDADAS ATÉ"):
            campo = "liquidado"
        else:
            continue
        if x["conta"] in FUNCOES:
            funcoes.setdefault(x["conta"], {"funcao": x["conta"]})[campo] = x["valor"]
        elif x["conta"].startswith("DESPESAS (EXCETO INTRA"):
            total[campo] = x["valor"]
    return {
        "ano": ano, "bimestre": bruto["periodo"], "total": total,
        "funcoes": sorted(funcoes.values(), key=lambda f: -(f.get("liquidado") or 0)),
    }


def _rgf_anexo1(ano):
    for periodicidade, periodos in (("Q", (3, 2, 1)), ("S", (2, 1))):
        for periodo in periodos:
            itens = (get_json(f"{BASE}/rgf", {
                "an_exercicio": ano, "in_periodicidade": periodicidade, "nr_periodo": periodo,
                "co_tipo_demonstrativo": "RGF", "no_anexo": "RGF-Anexo 01", "co_esfera": "M",
                "co_poder": "E", "id_ente": config.CODIGO_IBGE,
            }) or {}).get("items", [])
            if itens:
                return {"periodicidade": periodicidade, "periodo": periodo, "itens": itens}
    return None


def despesa_pessoal(ano):
    bruto = em_cache(config.CACHE / "siconfi" / f"rgf1_{ano}.json", lambda: _rgf_anexo1(ano), renovar=_renovar(ano))
    if not bruto:
        return None
    r = {"ano": ano, "periodo": bruto["periodo"], "periodicidade": bruto["periodicidade"]}
    mapa = {
        "ReceitaCorrenteLiquidaAjustada": "rcl_ajustada",
        "DespesaComPessoalTotal": "despesa_pessoal",
        "LimiteMaximoDespesaComPessoalTotal": "limite_maximo",
        "LimitePrudencialDespesaComPessoalTotal": "limite_prudencial",
        "LimiteDeAlertaDespesaComPessoalTotal": "limite_alerta",
    }
    for x in bruto["itens"]:
        chave = mapa.get(x["cod_conta"])
        if not chave:
            continue
        if x["coluna"] == "Valor":
            r[chave] = x["valor"]
        elif x["coluna"].startswith("%"):
            r[chave + "_pct"] = x["valor"]
    return r if "despesa_pessoal_pct" in r else None


# Composição da receita corrente (RREO Anexo 03, total dos últimos 12 meses)
CONTAS_RECEITA = [
    ("ReceitaTributariaLiquidaExcetoTransferenciasEFUNDEB", "Impostos e taxas do próprio município (ISS, IPTU, ITBI…)", "propria"),
    ("RREO3CotaParteDoFPM", "FPM (repasse federal)", "federal"),
    ("RREO3TransferenciasDoFUNDEB", "FUNDEB (educação)", "federal"),
    ("RREO3CotaParteDoICMS", "Cota do ICMS (repasse estadual)", "estadual"),
    ("RREO3CotaParteDoIPVA", "Cota do IPVA (repasse estadual)", "estadual"),
    ("RREO3OutrasTransferenciasCorrentes", "Outras transferências (SUS, FNDE, convênios, emendas…)", "federal"),
]


def _rreo_anexo3(ano):
    for periodo in range(6, 0, -1):
        itens = (get_json(f"{BASE}/rreo", {
            "an_exercicio": ano, "nr_periodo": periodo, "co_tipo_demonstrativo": "RREO",
            "no_anexo": "RREO-Anexo 03", "id_ente": config.CODIGO_IBGE,
        }) or {}).get("items", [])
        if itens:
            return {"periodo": periodo, "itens": itens}
    return None


def receitas(ano):
    bruto = em_cache(config.CACHE / "siconfi" / f"rreo3_{ano}.json", lambda: _rreo_anexo3(ano), renovar=_renovar(ano))
    if not bruto:
        return None
    valores = {x["cod_conta"]: x["valor"] for x in bruto["itens"] if x["coluna"].upper().startswith("TOTAL (")}
    total = valores.get("ReceitasCorrentesLiquidasExcetoTransferenciasEFUNDEB")
    if not total:
        return None
    fontes = [{"nome": nome, "origem": origem, "valor": valores.get(cod) or 0} for cod, nome, origem in CONTAS_RECEITA]
    fontes.append({"nome": "Demais receitas (serviços, contribuições, patrimônio…)", "origem": "propria",
                   "valor": max(0, total - sum(f["valor"] for f in fontes))})
    return {"ano": ano, "bimestre": bruto["periodo"], "total": total, "fontes": fontes}


# ---------- Saúde financeira: RREO Anexo 14 (demonstrativo simplificado), RGF Anexos 02 e 05 ----------
def _rreo_generico(ano, anexo):
    for periodo in range(6, 0, -1):
        itens = (get_json(f"{BASE}/rreo", {
            "an_exercicio": ano, "nr_periodo": periodo, "co_tipo_demonstrativo": "RREO",
            "no_anexo": anexo, "id_ente": config.CODIGO_IBGE,
        }) or {}).get("items", [])
        if itens:
            return {"periodo": periodo, "itens": itens}
    return None


def _rgf_generico(ano, anexo):
    for periodicidade, periodos in (("Q", (3, 2, 1)), ("S", (2, 1))):
        for periodo in periodos:
            itens = (get_json(f"{BASE}/rgf", {
                "an_exercicio": ano, "in_periodicidade": periodicidade, "nr_periodo": periodo,
                "co_tipo_demonstrativo": "RGF", "no_anexo": anexo, "co_esfera": "M",
                "co_poder": "E", "id_ente": config.CODIGO_IBGE,
            }) or {}).get("items", [])
            if itens:
                return {"periodicidade": periodicidade, "periodo": periodo, "itens": itens}
    return None


# (prefixo do cod_conta, início da coluna, campo de saída)
CAMPOS_ANEXO14 = [
    ("PrevisaoAtualizadaDemonstrativoSimplificado", "Até o Bimestre", "receita_prevista"),
    ("ReceitasRealizadasDemonstrativoSimplificado", "Até o Bimestre", "receita_realizada"),
    ("DespesasEmpenhadasDemonstrativoSimplificadoBalanco", "Até o Bimestre", "despesa_empenhada"),
    ("DespesasPagasDemonstrativoSimplificado", "Até o Bimestre", "despesa_paga"),
    ("TotalRestosAPagarDemonstrativoSimplificado", "Inscrição", "rp_inscritos"),
    ("TotalRestosAPagarDemonstrativoSimplificado", "Pagamento", "rp_pagos"),
    ("TotalRestosAPagarDemonstrativoSimplificado", "Saldo a Pagar", "rp_saldo"),
    ("MinimoAnualDasReceitasDeImpostosNaManutencao", "% Aplicado", "educacao_pct"),
    ("MinimoAnualDoFUNDEBNaRemuneracao", "% Aplicado", "fundeb_pct"),
    ("AplicacaoTotalDasDespesasComAcoesEServicosPublicosDeSaude", "% Aplicado", "saude_pct"),
    ("ResultadoPrevidenciarioRPPS", "Até o Bimestre", "previdencia_resultado"),
]


def saude_financeira(ano):
    """Indicadores de saúde financeira de um ano. Devolve None se não houver RREO Anexo 14."""
    renovar = _renovar(ano)
    a14 = em_cache(config.CACHE / "siconfi" / f"rreo14_{ano}.json", lambda: _rreo_generico(ano, "RREO-Anexo 14"), renovar=renovar)
    if not a14:
        return None
    r = {"ano": ano, "bimestre": a14["periodo"], "fechado": a14["periodo"] == 6}
    for x in a14["itens"]:
        for prefixo, coluna, campo in CAMPOS_ANEXO14:
            if x["cod_conta"].startswith(prefixo) and x["coluna"].startswith(coluna) and campo not in r:
                r[campo] = x["valor"]

    a5 = em_cache(config.CACHE / "siconfi" / f"rgf5_{ano}.json", lambda: _rgf_generico(ano, "RGF-Anexo 05"), renovar=renovar)
    for x in (a5 or {}).get("itens", []):
        total = x["conta"].startswith("TOTAL (IV)")
        livre = x["conta"].startswith("TOTAL DOS RECURSOS NÃO VINCULADOS")
        if x["cod_conta"] == "DisponibilidadeDeCaixaBruta" and total:
            r["caixa_bruto"] = x["valor"]
        elif x["cod_conta"] == "DisponibilidadeDeCaixaLiquidaAposRP" and total:
            r["caixa_liquido"] = x["valor"]
        elif x["cod_conta"] == "DisponibilidadeDeCaixaLiquidaAposRP" and livre:
            r["caixa_livre"] = x["valor"]

    a2 = em_cache(config.CACHE / "siconfi" / f"rgf2_{ano}.json", lambda: _rgf_generico(ano, "RGF-Anexo 02"), renovar=renovar)
    if a2:
        coluna = f"Até o {a2['periodo']}º"
        for x in a2["itens"]:
            if not x["coluna"].startswith(coluna):
                continue
            if x["cod_conta"] == "DividaConsolidada":
                r["divida"] = x["valor"]
            elif x["cod_conta"] == "PercentualDaDCLSobreARCL":
                r["divida_liquida_pct"] = x["valor"]
    return r
