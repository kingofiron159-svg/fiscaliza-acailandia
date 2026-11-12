"""Portal Nacional de Contratações Públicas (PNCP) - https://pncp.gov.br/api/consulta/swagger-ui/index.html"""
import calendar
import datetime as dt

from . import config
from .rede import em_cache, get_json

BASE = "https://pncp.gov.br/api/consulta/v1"

MODALIDADES = {
    1: "Leilão eletrônico", 2: "Diálogo competitivo", 3: "Concurso", 4: "Concorrência eletrônica",
    5: "Concorrência presencial", 6: "Pregão eletrônico", 7: "Pregão presencial", 8: "Dispensa",
    9: "Inexigibilidade", 10: "Manifestação de interesse", 11: "Pré-qualificação",
    12: "Credenciamento", 13: "Leilão presencial",
}


def _paginar(endpoint, params, tamanho):
    itens, pagina = [], 1
    while True:
        d = get_json(f"{BASE}/{endpoint}", {**params, "pagina": pagina, "tamanhoPagina": tamanho})
        if not d or not d.get("data"):
            break
        itens += d["data"]
        if d.get("paginasRestantes", 0) <= 0:
            break
        pagina += 1
    return itens


def _periodo_fechado(fim: dt.date) -> bool:
    """Períodos encerrados há mais de 60 dias ficam em cache; os recentes são baixados de novo."""
    return (dt.date.today() - fim).days > 60


def contratacoes_ano(ano: int, modalidade: int):
    hoje = dt.date.today()
    fim = min(dt.date(ano, 12, 31), hoje)
    arq = config.CACHE / "pncp" / "contratacoes" / f"{ano}_{modalidade:02d}.json"
    return em_cache(
        arq,
        lambda: _paginar("contratacoes/publicacao", {
            "dataInicial": f"{ano}0101", "dataFinal": fim.strftime("%Y%m%d"),
            "codigoModalidadeContratacao": modalidade, "codigoMunicipioIbge": config.CODIGO_IBGE,
        }, 50),
        renovar=not _periodo_fechado(fim),
    )


def contratos_mes(cnpj: str, ano: int, mes: int):
    ini = dt.date(ano, mes, 1)
    fim = min(dt.date(ano, mes, calendar.monthrange(ano, mes)[1]), dt.date.today())
    arq = config.CACHE / "pncp" / "contratos" / cnpj / f"{ano}_{mes:02d}.json"
    return em_cache(
        arq,
        lambda: _paginar("contratos", {
            "dataInicial": ini.strftime("%Y%m%d"), "dataFinal": fim.strftime("%Y%m%d"), "cnpjOrgao": cnpj,
        }, 500),
        renovar=not _periodo_fechado(fim),
    )


def link_contrato(c):
    cnpj = c["orgaoEntidade"]["cnpj"]
    return f"https://pncp.gov.br/app/contratos/{cnpj}/{c['anoContrato']}/{c['sequencialContrato']}"


def link_compra(numero_controle: str):
    # formato: 07000268000172-1-000111/2025
    try:
        cnpj, _, resto = numero_controle.split("-", 2)
        seq, ano = resto.split("/")
        return f"https://pncp.gov.br/app/editais/{cnpj}/{ano}/{int(seq)}"
    except ValueError:
        return None
