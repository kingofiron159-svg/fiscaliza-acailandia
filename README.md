# Fiscaliza Açailândia

Projeto cidadão independente que reúne dados **públicos e oficiais** sobre contratos e gastos da
Prefeitura de Açailândia (MA) e aponta automaticamente pontos que merecem atenção.

> Não é um site oficial. Alertas são indícios calculados por regras objetivas e **não são acusações**.

## O que o site mostra

- **Início:** total contratado, gastos por mês, quanto foi contratado sem licitação, maiores secretarias e fornecedores.
- **Alertas:** empresas punidas (CEIS/CNEP), empresas recém-abertas, CNPJ irregular, MEI acima do limite, capital social baixo,
  possível fracionamento de dispensas, contratação direta de alto valor, concentração em um fornecedor,
  sócios em comum e gasto com pessoal acima dos limites da LRF.
- **Contratos e fornecedores:** busca, filtros e link para cada documento no PNCP.
- **Preços:** busca do preço unitário pago por item, licitações com menor desconto e mesmo item com preços diferentes.
- **Orçamento:** saúde financeira (mínimos de educação e saúde, caixa, restos a pagar, dívida), gasto por área e despesa com pessoal × LRF.
- **Glossário:** 49 termos explicados em linguagem simples, com a base legal; botões "?" abrem a explicação em qualquer página.
- **Verbas e emendas:** de onde vem a receita da Prefeitura e as emendas parlamentares recebidas (quem mandou, quanto, para quê).

## Fontes

| Dado | Fonte |
|---|---|
| Licitações e contratos | [PNCP – API de consulta](https://pncp.gov.br/api/consulta/swagger-ui/index.html) |
| Orçamento (RREO) e pessoal (RGF) | [SICONFI – Tesouro Nacional](https://apidatalake.tesouro.gov.br/docs/siconfi/) |
| Emendas parlamentares | [Portal da Transparência / CGU – dados abertos](https://portaldatransparencia.gov.br/download-de-dados/emendas-parlamentares) |
| Empresas punidas (CEIS, CNEP) | [Portal da Transparência / CGU – dados abertos](https://portaldatransparencia.gov.br/download-de-dados) |
| Dados das empresas | Base pública de CNPJ da Receita Federal (via minhareceita.org / BrasilAPI) |

## Como rodar no seu computador

Precisa apenas do Python 3.10+ (não há dependências para instalar).

```bash
python coletar.py                                   # baixa os dados e gera site/dados/dados.json
python -m http.server 8765 --directory site         # abre o site em http://localhost:8765
```

A primeira coleta leva de 10 a 30 minutos, porque a API do PNCP é lenta. As próximas reaproveitam a pasta
`cache/` e só baixam de novo os meses recentes.

## Como publicar (de graça) no GitHub Pages

1. Crie um repositório público no GitHub e envie esta pasta.
2. Em **Settings → Pages**, escolha **Source: GitHub Actions**.
3. Em **Actions**, rode o fluxo "Atualizar dados e publicar site" (ou espere o próximo push).
4. O site fica em `https://SEU-USUARIO.github.io/NOME-DO-REPO/` e se atualiza sozinho todo dia às 6h.

## Ajustes

Tudo fica em [`fiscaliza/config.py`](fiscaliza/config.py): código IBGE, CNPJ da prefeitura, ano inicial,
limites de dispensa (atualize quando sair o decreto do ano) e os parâmetros de cada alerta.
Para fiscalizar **outra cidade**, troque `CIDADE`, `UF`, `CODIGO_IBGE` e `CNPJ_PREFEITURA`.

## Limitações conhecidas

- Só entram contratos publicados no PNCP (obrigatório desde a Lei 14.133/2021).
- O valor exibido é o valor global do contrato, não o efetivamente pago.
- Termos aditivos ainda não são analisados.
- Dados de CNPJ refletem a situação atual na Receita.
