"""Empresas punidas: cadastros CEIS e CNEP da CGU (Portal da Transparência, dados abertos).

CEIS - Cadastro de Empresas Inidôneas e Suspensas (proibições de licitar/contratar).
CNEP - Cadastro Nacional de Empresas Punidas (Lei Anticorrupção, 12.846/2013).
Os arquivos são publicados diariamente e não exigem chave de acesso.
"""
import csv
import datetime as dt
import io
import urllib.request
import zipfile

from . import config
from .rede import em_cache

URL = "https://portaldatransparencia.gov.br/download-de-dados/{base}/{data}"
BASES = ("ceis", "cnep")


def _iso(s):
    try:
        return dt.datetime.strptime(s.strip(), "%d/%m/%Y").date().isoformat()
    except (ValueError, AttributeError):
        return None


def _baixar(base):
    """Baixa o arquivo mais recente (tenta hoje e os 7 dias anteriores)."""
    ultimo_erro = None
    for atras in range(8):
        dia = dt.date.today() - dt.timedelta(days=atras)
        try:
            req = urllib.request.Request(URL.format(base=base, data=dia.strftime("%Y%m%d")),
                                         headers={"User-Agent": "Mozilla/5.0 (FiscalizaCidadao)"})
            with urllib.request.urlopen(req, timeout=120) as r:
                z = zipfile.ZipFile(io.BytesIO(r.read()))
            texto = z.read(z.namelist()[0]).decode("latin-1")
            return dia, list(csv.DictReader(io.StringIO(texto), delimiter=";"))
        except Exception as e:  # dia sem arquivo, zip inválido, rede
            ultimo_erro = e
    raise RuntimeError(f"Não foi possível baixar o cadastro {base.upper()}: {ultimo_erro}")


def _carregar(base):
    dia, linhas = _baixar(base)
    sancoes = []
    for l in linhas:
        doc = "".join(ch for ch in (l.get("CPF OU CNPJ DO SANCIONADO") or "") if ch.isdigit())
        if (l.get("TIPO DE PESSOA") or "").strip().upper() != "J" or len(doc) != 14:
            continue  # só pessoas jurídicas: CPFs vêm mascarados e nomes geram homônimos
        sancoes.append({
            "cnpj": doc,
            "cadastro": base.upper(),
            "categoria": (l.get("CATEGORIA DA SANÇÃO") or "").strip(),
            "inicio": _iso(l.get("DATA INÍCIO SANÇÃO")),
            "fim": _iso(l.get("DATA FINAL SANÇÃO")),
            "orgao": (l.get("ÓRGÃO SANCIONADOR") or "").strip(),
            "uf": (l.get("UF ÓRGÃO SANCIONADOR") or "").strip(),
            "abrangencia": (l.get("ABRAGÊNCIA DA SANÇÃO") or l.get("ABRANGÊNCIA DA SANÇÃO") or "").strip(),
            "processo": (l.get("NÚMERO DO PROCESSO") or "").strip(),
            "fundamento": (l.get("FUNDAMENTAÇÃO LEGAL") or "").strip()[:140],
        })
    return {"data_arquivo": dia.isoformat(), "sancoes": sancoes}


def por_raiz_cnpj():
    """Devolve ({raiz de 8 dígitos do CNPJ: [sanções]}, {base: data do arquivo}).

    A sanção atinge a pessoa jurídica inteira (matriz e filiais), por isso a busca é pela raiz.
    O resultado fica em cache por dia.
    """
    indice, datas = {}, {}
    hoje = dt.date.today().isoformat()
    for base in BASES:
        dados = em_cache(config.CACHE / "sancoes" / f"{base}_{hoje}.json", lambda b=base: _carregar(b))
        datas[base] = dados["data_arquivo"]
        for s in dados["sancoes"]:
            indice.setdefault(s["cnpj"][:8], []).append(s)
    return indice, datas
