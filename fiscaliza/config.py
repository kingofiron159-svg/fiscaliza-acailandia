"""Configurações do projeto. Para fiscalizar outra cidade, troque os dados abaixo."""
from pathlib import Path

CIDADE = "Açailândia"
UF = "MA"
CODIGO_IBGE = "2100055"
CNPJ_PREFEITURA = "07000268000172"

# Primeiro ano coletado (o PNCP passou a ser obrigatório para municípios em 2023/2024).
ANO_INICIAL = 2023

RAIZ = Path(__file__).resolve().parent.parent
CACHE = RAIZ / "cache"            # respostas brutas das APIs (não vai para o site)
SAIDA = RAIZ / "site" / "dados"   # JSONs que o site lê

# Limites de dispensa por valor (Lei 14.133/2021, art. 75, I e II), atualizados por decreto
# todo ano. Confira o decreto vigente e atualize quando sair um novo.
LIMITES_DISPENSA = {
    # ano: (inciso I - obras/engenharia/manut. veículos, inciso II - demais compras/serviços)
    2023: (114_416.65, 57_208.33),   # Decreto 11.317/2022
    2024: (119_812.02, 59_906.02),   # Decreto 11.871/2023
    2025: (125_451.15, 62_725.59),   # Decreto 12.343/2024
}

# Unificação de nomes de secretarias: (trecho sem acento e em maiúsculas, nome exibido no site).
# Vale a primeira regra que casar. Secretaria e o respectivo Fundo Municipal são somados, porque
# o fundo é o "caixa" da secretaria. Nomes que não casam com nenhuma regra ficam como estão.
REGRAS_UNIDADES = [
    ("EDUCACAO", "Secretaria Municipal de Educação"),
    ("FUNDO MUNICIPAL DE SAUDE", "Saúde (Secretaria e Fundo Municipal)"),
    ("SECRETARIA MUNICIPAL DE SAUDE", "Saúde (Secretaria e Fundo Municipal)"),
    ("ASSISTENCIA SOCIAL", "Assistência Social (Secretaria e Fundo Municipal)"),
    ("TRANSITO E TRANSPORTE", "Fundo Municipal de Trânsito e Transporte"),
    ("INDUSTRIA, COMERCIO E TURISMO", "Secretaria Municipal de Indústria, Comércio e Turismo"),
    ("CAMARA MUNICIPAL", "Câmara Municipal"),
    ("PROCURADORIA GERAL", "Procuradoria Geral do Município"),
    ("MUNICIPIO DE ACAILANDIA", "Prefeitura (secretaria não informada)"),
]

# Limite anual de faturamento do MEI (LC 123/2006).
LIMITE_MEI = 81_000.00

# Parâmetros dos alertas
DIAS_EMPRESA_NOVA = 180          # empresa aberta há menos de X dias quando assinou
VALOR_MIN_EMPRESA_NOVA = 30_000
CAPITAL_PROPORCAO_MIN = 0.10     # capital social < 10% do valor contratado no ano
VALOR_MIN_CAPITAL = 200_000
CONCENTRACAO_MIN = 0.40          # fornecedor com > 40% do valor de uma secretaria no ano
VALOR_MIN_CONCENTRACAO = 500_000
VALOR_DIRETA_ALTA = 1_000_000    # dispensa/inexigibilidade acima disso


def limites_dispensa(ano: int):
    """Limites do ano; se o decreto do ano não estiver cadastrado, usa o mais recente anterior."""
    anos = sorted(LIMITES_DISPENSA)
    conhecidos = [a for a in anos if a <= ano] or anos[:1]
    return LIMITES_DISPENSA[conhecidos[-1]]
