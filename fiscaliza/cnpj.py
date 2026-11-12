"""Dados cadastrais de CNPJ (base aberta da Receita Federal) via minhareceita.org, com BrasilAPI de reserva."""
import time

from . import config
from .rede import em_cache, get_json

FONTES = ("https://minhareceita.org/{}", "https://brasilapi.com.br/api/cnpj/v1/{}")


def _buscar(cnpj):
    for fonte in FONTES:
        try:
            d = get_json(fonte.format(cnpj), tentativas=2, timeout=40)
            if d and d.get("cnpj"):
                return _resumir(d)
        except RuntimeError:
            pass
        time.sleep(1)
    return {"cnpj": cnpj, "erro": "não encontrado"}


def _resumir(d):
    return {
        "cnpj": d.get("cnpj"),
        "razao_social": d.get("razao_social"),
        "nome_fantasia": d.get("nome_fantasia"),
        "abertura": d.get("data_inicio_atividade"),
        "situacao": d.get("descricao_situacao_cadastral"),
        "data_situacao": d.get("data_situacao_cadastral"),
        "capital_social": d.get("capital_social"),
        "porte": d.get("porte"),
        "mei": bool(d.get("opcao_pelo_mei")),
        "cnae": d.get("cnae_fiscal_descricao"),
        "municipio": d.get("municipio"),
        "uf": d.get("uf"),
        "natureza": d.get("natureza_juridica"),
        # só o nome dos sócios; o CPF já vem mascarado na base pública e não é exibido
        "socios": [s.get("nome_socio") for s in (d.get("qsa") or []) if s.get("nome_socio")],
    }


def consultar(cnpj: str):
    return em_cache(config.CACHE / "cnpj" / f"{cnpj}.json", lambda: _buscar(cnpj))
