"""Unifica os nomes de secretarias/órgãos, que a Prefeitura cadastra no PNCP com grafias diferentes.

As regras ficam em config.REGRAS_UNIDADES: lista de (trecho, nome unificado). O trecho é comparado
sem acentos e em maiúsculas; vale a primeira regra que casar. O nome original é preservado no
contrato (campo `unidade_original`) e continua visível no detalhe.
"""
import re
import unicodedata

from . import config


def _chave(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn").upper()
    return re.sub(r"\s+", " ", s).strip()


def unificar(unidade, orgao):
    original = re.sub(r"\s+", " ", unidade or orgao or "").strip()
    chave = _chave(original)
    for trecho, nome in config.REGRAS_UNIDADES:
        if trecho in chave:
            return nome
    return original
