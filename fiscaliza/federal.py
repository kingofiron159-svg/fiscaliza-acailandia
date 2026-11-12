"""Dinheiro federal que chega à cidade por emendas parlamentares.

Fonte: Portal da Transparência (CGU), arquivo aberto "Emendas Parlamentares" (sem chave de acesso).
O zip traz três tabelas: por localidade de aplicação, por favorecido (quem recebeu) e convênios.
"""
import csv
import datetime as dt
import io
import urllib.request
import zipfile
from collections import defaultdict

from . import config
from .rede import em_cache

URL = "https://portaldatransparencia.gov.br/download-de-dados/emendas-parlamentares/UNICO"
NATUREZAS_PUBLICAS = ("município", "fundo público", "autarquia", "órgão público", "fundação pública")


def _num(s):
    try:
        return float((s or "0").replace(".", "").replace(",", "."))
    except ValueError:
        return 0.0


def _linhas(z, nome):
    with z.open(nome) as f:
        yield from csv.DictReader(io.TextIOWrapper(f, encoding="latin-1"), delimiter=";")


def _baixar_e_extrair():
    destino = config.CACHE / "federal" / "emendas.zip"
    destino.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0 (FiscalizaCidadao)"})
    with urllib.request.urlopen(req, timeout=600) as r, open(destino, "wb") as f:
        while bloco := r.read(1 << 20):
            f.write(bloco)

    cidade = config.CIDADE.upper()
    local = f"{cidade} - {config.UF}"
    with zipfile.ZipFile(destino) as z:
        # 1) Quem recebeu: favorecidos sediados na cidade. Pessoas físicas ficam de fora (privacidade).
        recebidos, codigos = [], set()
        for r in _linhas(z, "EmendasParlamentares_PorFavorecido.csv"):
            if r["UF Favorecido"] != config.UF or r["Município Favorecido"].strip().upper() != cidade:
                continue
            if r["Tipo Favorecido"].strip().lower() != "pessoa jurídica":
                continue
            natureza = r["Natureza Jurídica"].strip()
            recebidos.append({
                "emenda": r["Código da Emenda"].strip(),
                "autor": r["Nome do Autor da Emenda"].strip().title(),
                "tipo": r["Tipo de Emenda"].strip(),
                "ano": int(r["Ano/Mês"][:4]), "mes": r["Ano/Mês"][:4] + "-" + r["Ano/Mês"][4:6],
                "cnpj": "".join(ch for ch in r["Código do Favorecido"] if ch.isdigit()),
                "favorecido": r["Favorecido"].strip(),
                "natureza": natureza,
                "publico": natureza.lower().startswith(NATUREZAS_PUBLICAS),
                "valor": _num(r["Valor Recebido"]),
            })
            codigos.add(r["Código da Emenda"].strip())

        # 2) Para que área era cada emenda (função e ação orçamentária)
        areas = defaultdict(lambda: {"funcoes": set(), "acoes": set()})
        aplicadas = []
        for r in _linhas(z, "EmendasParlamentares.csv"):
            cod = r["Código da Emenda"].strip()
            if cod in codigos:
                areas[cod]["funcoes"].add(r["Nome Função"].strip())
                areas[cod]["acoes"].add(r["Nome Ação"].strip().capitalize())
            if r["Código Município IBGE"].strip() == config.CODIGO_IBGE:
                aplicadas.append({
                    "emenda": cod, "ano": int(r["Ano da Emenda"]), "tipo": r["Tipo de Emenda"].strip(),
                    "autor": r["Nome do Autor da Emenda"].strip().title(), "funcao": r["Nome Função"].strip(),
                    "acao": r["Nome Ação"].strip().capitalize(),
                    "empenhado": _num(r["Valor Empenhado"]),
                    "pago": _num(r["Valor Pago"]) + _num(r["Valor Restos A Pagar Pagos"]),
                })
        for r in recebidos:
            a = areas.get(r["emenda"])
            r["funcao"] = " / ".join(sorted(a["funcoes"])) if a else None
            r["acao"] = "; ".join(sorted(a["acoes"]))[:200] if a else None

        # 3) Convênios firmados com recursos de emendas
        convenios = []
        for r in _linhas(z, "EmendasParlamentares_Convenios.csv"):
            if not r["Localidade do gasto"].strip().upper().startswith(local):
                continue
            try:
                data = dt.datetime.strptime(r["Data Publicação Convênio"].strip(), "%d/%m/%Y").date().isoformat()
            except ValueError:
                data = None
            convenios.append({
                "emenda": r["Código da Emenda"].strip(), "numero": r["Número Convênio"].strip(), "data": data,
                "convenente": r["Convenente"].strip(), "objeto": r["Objeto Convênio"].strip().capitalize(),
                "funcao": r["Nome Função"].strip(), "valor": _num(r["Valor Convênio"]),
            })

    recebidos.sort(key=lambda r: r["mes"], reverse=True)
    convenios.sort(key=lambda c: c["data"] or "", reverse=True)
    return {"atualizado_em": dt.date.today().isoformat(), "recebidos": recebidos,
            "aplicadas": aplicadas, "convenios": convenios}


def emendas():
    """Resultado em cache por dia (o arquivo da CGU tem dezenas de MB)."""
    hoje = dt.date.today().isoformat()
    return em_cache(config.CACHE / "federal" / f"emendas_{hoje}.json", _baixar_e_extrair)
