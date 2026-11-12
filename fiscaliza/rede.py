"""Acesso HTTP com novas tentativas e cache em disco."""
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

UA = "FiscalizaCidadao/0.1 (projeto independente de transparencia publica)"


def get_json(url, params=None, tentativas=4, timeout=150):
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    ultimo_erro = None
    for i in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                corpo = r.read()
                if r.status == 204 or not corpo:
                    return None
                return json.loads(corpo.decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (400, 404):
                return None
            ultimo_erro = e
            if e.code == 429:
                time.sleep(15 * (i + 1))
        except Exception as e:  # timeout, conexão, JSON inválido
            ultimo_erro = e
        time.sleep(3 * (i + 1))
    raise RuntimeError(f"Falha ao acessar {url}: {ultimo_erro}")


def ler_json(caminho: Path):
    with open(caminho, encoding="utf-8") as f:
        return json.load(f)


def salvar_json(caminho: Path, dados, compacto=False):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        if compacto:
            json.dump(dados, f, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(dados, f, ensure_ascii=False, indent=1)
    tmp.replace(caminho)


def em_cache(caminho: Path, buscar, renovar=False):
    """Devolve o conteúdo de `caminho` se existir; senão chama buscar() e salva."""
    if caminho.exists() and not renovar:
        return ler_json(caminho)
    dados = buscar()
    salvar_json(caminho, dados)
    return dados
