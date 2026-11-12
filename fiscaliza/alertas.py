"""Regras automáticas que apontam contratos que merecem um olhar mais atento.

Um alerta NÃO é prova de irregularidade: é um indício objetivo, calculado a partir de dados
públicos, que pode ter explicação legítima. Cada alerta diz qual critério foi usado.
"""
import datetime as dt
import re
from collections import defaultdict

from . import config


def _data(s):
    try:
        return dt.date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return None


def _brl(v):
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _pct(v):
    return f"{v:.2f}".rstrip("0").rstrip(".").replace(".", ",") + "%"


INCISO_DISPENSA =re.compile(r"Art\. 75, (I|II)$")


def gerar(contratos, fornecedores, pessoal, extras=(), financas=()):
    alertas = list(extras)

    def add(tipo, gravidade, titulo, descricao, ni=None, valor=None, ano=None, ids=()):
        alertas.append({
            "tipo": tipo, "gravidade": gravidade, "titulo": titulo, "descricao": descricao,
            "ni": ni, "fornecedor": (fornecedores.get(ni) or {}).get("nome") if ni else None,
            "valor": valor, "ano": ano, "contratos": list(ids),
        })

    por_fornecedor = defaultdict(list)
    for c in contratos:
        por_fornecedor[c["ni"]].append(c)

    for ni, lista in por_fornecedor.items():
        cad = (fornecedores.get(ni) or {}).get("cadastro") or {}
        nome = (fornecedores.get(ni) or {}).get("nome")
        abertura = _data(cad.get("abertura"))

        # 1. Empresa recém-aberta ao assinar o contrato
        if abertura:
            novos = [c for c in lista if _data(c["assinatura"]) and
                     0 <= (_data(c["assinatura"]) - abertura).days <= config.DIAS_EMPRESA_NOVA]
            total = sum(c["valor"] for c in novos)
            if novos and total >= config.VALOR_MIN_EMPRESA_NOVA:
                dias = min((_data(c["assinatura"]) - abertura).days for c in novos)
                add("empresa_nova", "alta" if total >= 100_000 else "media",
                    "Empresa recém-aberta",
                    f"{nome} foi aberta em {abertura:%d/%m/%Y} e assinou contrato(s) somando {_brl(total)} "
                    f"apenas {dias} dias depois. Empresas sem histórico ganhando contratos merecem verificação "
                    f"de capacidade técnica e de quem são os sócios.",
                    ni, total, None, [c["id"] for c in novos])

        # 2. Situação cadastral irregular
        situacao = (cad.get("situacao") or "").upper()
        if situacao and situacao != "ATIVA":
            data_sit = _data(cad.get("data_situacao"))
            antes = [c for c in lista if data_sit and _data(c["assinatura"]) and _data(c["assinatura"]) >= data_sit]
            if antes:
                add("situacao_cnpj", "alta", f"Contrato com CNPJ {situacao.lower()}",
                    f"O CNPJ de {nome} está {situacao} na Receita Federal desde {data_sit:%d/%m/%Y}, "
                    f"e houve contrato assinado depois dessa data.",
                    ni, sum(c["valor"] for c in antes), None, [c["id"] for c in antes])
            else:
                add("situacao_cnpj", "baixa", f"Fornecedor hoje com CNPJ {situacao.lower()}",
                    f"O CNPJ de {nome} aparece como {situacao} na Receita Federal"
                    + (f" desde {data_sit:%d/%m/%Y}" if data_sit else "") +
                    ". Os contratos foram assinados antes disso, mas convém verificar se ainda há pagamentos.",
                    ni, sum(c["valor"] for c in lista), None, [c["id"] for c in lista])

        # 2b. Empresa punida (CEIS / CNEP): um alerta por empresa, com a gravidade da sanção mais séria
        sancoes = (fornecedores.get(ni) or {}).get("sancoes", [])
        if sancoes:
            niveis = {"alta": [], "media": [], "baixa": []}
            afetados = {"alta": {}, "media": {}}
            for s in sancoes:
                ini, fim = _data(s.get("inicio")), _data(s.get("fim"))
                categoria = s["categoria"].lower()
                restritiva = any(p in categoria for p in ("impedi", "suspens", "inid", "proibi"))
                durante = [c for c in lista if ini and _data(c["assinatura"])
                           and ini <= _data(c["assinatura"]) <= (fim or dt.date.max)]
                if restritiva and durante:
                    ampla = "todas as esferas" in (s.get("abrangencia") or "").lower() or "inid" in categoria
                    nivel = "alta" if ampla else "media"
                    afetados[nivel].update({c["id"]: c for c in durante})
                else:
                    nivel = "baixa"
                niveis[nivel].append(s)

            def resumo(s):
                ini, fim = _data(s.get("inicio")), _data(s.get("fim"))
                return (f"\"{s['categoria']}\" aplicada por {s['orgao'] or 'órgão não informado'}"
                        f"{'/' + s['uf'] if s.get('uf') else ''}, "
                        + (f"de {ini:%d/%m/%Y}" if ini else "sem data de início")
                        + (f" a {fim:%d/%m/%Y}" if fim else ", sem data final")
                        + f" (abrangência: {s.get('abrangencia') or 'não informada'})")

            nivel = next(n for n in ("alta", "media", "baixa") if niveis[n])
            principais = niveis[nivel]
            outras = len(sancoes) - 1
            texto = (f"{nome} consta no {principais[0]['cadastro']} (cadastro de empresas punidas da CGU): "
                     f"{resumo(principais[0])}."
                     + (f" Há mais {outras} sanção(ões) registrada(s) para a empresa." if outras else ""))
            if nivel == "baixa":
                add("sancao", "baixa", "Fornecedor com punição registrada",
                    texto + " Os contratos com o município foram assinados fora do período das sanções, "
                    "ou a punição não proíbe contratar. Fica como histórico do fornecedor.",
                    ni, sum(c["valor"] for c in lista), None, [c["id"] for c in lista])
            else:
                cs = list(afetados[nivel].values())
                add("sancao", nivel,
                    "Contrato com empresa proibida de contratar" if nivel == "alta"
                    else "Contrato com empresa punida por outro órgão",
                    texto + f" {len(cs)} contrato(s) com o município foram assinados durante a vigência. "
                    + ("Com abrangência em todas as esferas, a empresa não poderia ser contratada por nenhum órgão público."
                       if nivel == "alta" else
                       "Em regra, esse tipo de sanção só impede contratos com o ente que puniu, então o contrato "
                       "pode ser legal; mas é um histórico que justifica acompanhar a execução de perto."),
                    ni, sum(c["valor"] for c in cs), None, [c["id"] for c in cs])

        por_ano = defaultdict(list)
        for c in lista:
            por_ano[c["ano"]].append(c)
        for ano, cs in por_ano.items():
            total_ano = sum(c["valor"] for c in cs)

            # 3. MEI recebendo acima do limite de faturamento
            if cad.get("mei") and total_ano > config.LIMITE_MEI:
                add("mei_acima_limite", "alta", "MEI com contratos acima do limite anual",
                    f"{nome} é optante do MEI, cujo faturamento máximo é {_brl(config.LIMITE_MEI)} por ano, "
                    f"mas tem contratos com o município somando {_brl(total_ano)} em {ano}.",
                    ni, total_ano, ano, [c["id"] for c in cs])

            # 4. Capital social muito baixo frente ao valor contratado
            capital = cad.get("capital_social")
            if (capital is not None and total_ano >= config.VALOR_MIN_CAPITAL
                    and capital < total_ano * config.CAPITAL_PROPORCAO_MIN):
                add("capital_baixo", "media", "Capital social baixo para o valor contratado",
                    f"{nome} tem capital social de {_brl(capital or 0)} e contratou {_brl(total_ano)} "
                    f"com o município em {ano}. Pode indicar empresa sem estrutura para executar o serviço.",
                    ni, total_ano, ano, [c["id"] for c in cs])

            # 5. Possível fracionamento de dispensa por valor
            grupos = defaultdict(list)
            for c in cs:
                m = INCISO_DISPENSA.search(c.get("amparo") or "")
                if c["modalidade"] == "Dispensa" and m:
                    grupos[(c["orgao"], m.group(1))].append(c)
            for (orgao, inciso), dc in grupos.items():
                limite = config.limites_dispensa(ano)[0 if inciso == "I" else 1]
                soma = sum(c["valor"] for c in dc)
                if len(dc) >= 2 and soma > limite:
                    add("fracionamento", "media", "Possível fracionamento de despesa",
                        f"{nome} recebeu {len(dc)} contratos por dispensa de licitação (art. 75, {inciso}) em {ano}, "
                        f"somando {_brl(soma)}, acima do limite anual de {_brl(limite)} para esse tipo de dispensa. "
                        f"Dividir compras para fugir da licitação é proibido (art. 75, §1º). Pode ser legítimo se "
                        f"forem objetos de naturezas diferentes.",
                        ni, soma, ano, [c["id"] for c in dc])

            # 6. Contratação direta de valor alto
            for c in cs:
                if c["modalidade"] in ("Dispensa", "Inexigibilidade") and c["valor"] >= config.VALOR_DIRETA_ALTA:
                    add("direta_alta", "baixa", f"{c['modalidade']} de valor elevado",
                        f"Contrato de {_brl(c['valor'])} com {nome} sem licitação ({c['modalidade'].lower()}"
                        f"{', ' + c['amparo'] if c.get('amparo') else ''}). Vale conferir a justificativa no processo.",
                        ni, c["valor"], ano, [c["id"]])

    # 7. Concentração em um fornecedor dentro de uma secretaria
    por_unidade = defaultdict(lambda: defaultdict(list))
    for c in contratos:
        por_unidade[(c["unidade"] or c["orgao"], c["ano"])][c["ni"]].append(c)
    for (unidade, ano), forn in por_unidade.items():
        total = sum(c["valor"] for cs in forn.values() for c in cs)
        if total <= 0:
            continue
        for ni, cs in forn.items():
            v = sum(c["valor"] for c in cs)
            if v >= config.VALOR_MIN_CONCENTRACAO and v / total >= config.CONCENTRACAO_MIN and len(forn) > 1:
                nome = (fornecedores.get(ni) or {}).get("nome")
                add("concentracao", "baixa", "Alta concentração em um fornecedor",
                    f"{nome} ficou com {v / total:.0%} de todo o valor contratado por {unidade} em {ano} "
                    f"({_brl(v)} de {_brl(total)}).", ni, v, ano, [c["id"] for c in cs])

    # 8. Sócios com o mesmo nome em fornecedores diferentes
    socio_para = defaultdict(set)
    for ni, f in fornecedores.items():
        for s in (f.get("cadastro") or {}).get("socios", []):
            socio_para[s.strip().upper()].add(ni)
    for socio, nis in socio_para.items():
        if 2 <= len(nis) <= 6:
            nomes = sorted((fornecedores[n].get("nome") or n) for n in nis)
            total = sum(c["valor"] for n in nis for c in por_fornecedor[n])
            add("socio_comum", "baixa", "Fornecedores com sócio de mesmo nome",
                f"As empresas {', '.join(nomes)} têm um sócio chamado {socio.title()}. Se essas empresas "
                f"disputaram as mesmas licitações, pode não ter havido concorrência real. "
                f"Atenção: pode ser apenas um homônimo.",
                None, total, None, [c["id"] for n in nis for c in por_fornecedor[n]])

    # 9. Despesa com pessoal acima dos limites da LRF
    for p in pessoal:
        pct = p.get("despesa_pessoal_pct")
        if pct is None:
            continue
        rotulo = f"{p['periodo']}º {'quadrimestre' if p['periodicidade'] == 'Q' else 'semestre'} de {p['ano']}"
        if pct >= p.get("limite_maximo_pct", 54):
            g, txt = "alta", "acima do LIMITE MÁXIMO"
        elif pct >= p.get("limite_prudencial_pct", 51.3):
            g, txt = "alta", "acima do limite prudencial"
        elif pct >= p.get("limite_alerta_pct", 48.6):
            g, txt = "media", "acima do limite de alerta"
        else:
            continue
        add("lrf_pessoal", g, f"Gasto com pessoal {txt} da LRF",
            f"No {rotulo}, a despesa com pessoal do Executivo foi {_pct(pct)} da Receita Corrente Líquida, "
            f"{txt} (alerta {_pct(p.get('limite_alerta_pct', 48.6))}, prudencial "
            f"{_pct(p.get('limite_prudencial_pct', 51.3))}, máximo {_pct(p.get('limite_maximo_pct', 54))}).",
            None, p.get("despesa_pessoal"), p["ano"])

    # 10. Saúde financeira: mínimos constitucionais e caixa (só anos fechados, 6º bimestre)
    for f in financas:
        if not f.get("fechado"):
            continue
        ano = f["ano"]
        for campo, minimo, nome, base in (
            ("educacao_pct", 25, "educação", "art. 212 da Constituição"),
            ("saude_pct", 15, "saúde", "LC 141/2012, art. 7º"),
            ("fundeb_pct", 70, "remuneração dos profissionais da educação com o FUNDEB", "Lei 14.113/2020, art. 26"),
        ):
            pct = f.get(campo)
            if pct is not None and pct < minimo:
                add("minimo_constitucional", "alta", f"Mínimo de {nome} não cumprido em {ano}",
                    f"Em {ano} o município aplicou {_pct(pct)} em {nome}, abaixo do mínimo obrigatório de "
                    f"{minimo}% ({base}). O descumprimento pode levar à rejeição das contas e ao bloqueio de "
                    f"repasses.", None, None, ano)
            elif pct is not None and campo != "fundeb_pct" and pct < minimo + 0.5:
                add("minimo_constitucional", "baixa", f"Mínimo de {nome} cumprido no limite em {ano}",
                    f"Em {ano} o município declarou ter aplicado {_pct(pct)} em {nome}; o mínimo obrigatório é "
                    f"{minimo}% ({base}). Com margem tão estreita, qualquer despesa glosada pelo Tribunal de "
                    f"Contas faz o índice cair abaixo do mínimo. Vale acompanhar o parecer do TCE.",
                    None, None, ano)
        livre = f.get("caixa_livre")
        if livre is not None and livre < 0:
            add("caixa_negativo", "media", f"Caixa livre negativo ao fim de {ano}",
                f"Ao fim de {ano}, depois de descontadas as obrigações, faltavam {_brl(-livre)} nos recursos "
                f"não vinculados (os que a Prefeitura pode usar livremente). Significa que há contas a pagar "
                f"sem dinheiro em caixa para cobri-las.", None, -livre, ano)
        prev, real = f.get("receita_prevista"), f.get("receita_realizada")
        if prev and real and real < prev * 0.9:
            add("receita_frustrada", "baixa", f"Arrecadação bem abaixo do previsto em {ano}",
                f"O orçamento de {ano} previa {_brl(prev)} de receita e entraram {_brl(real)} "
                f"({real / prev:.0%}). Orçamento superestimado autoriza gastos sem dinheiro para pagá-los.",
                None, prev - real, ano)

    ordem = {"alta": 0, "media": 1, "baixa": 2}
    alertas.sort(key=lambda a: (ordem[a["gravidade"]], -(a["valor"] or 0)))
    for i, a in enumerate(alertas, 1):
        a["id"] = i
    return alertas
