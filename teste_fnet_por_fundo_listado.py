import csv
import json
import sys
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


BASE = "https://fnet.bmfbovespa.com.br/fnet/publico/pesquisarGerenciadorDocumentosDados"
CSV_FUNDOS = "fundosListados.csv"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://fnet.bmfbovespa.com.br/fnet/publico/abrirGerenciadorDocumentosCVM",
    "X-Requested-With": "XMLHttpRequest",
    "Origin": "https://fnet.bmfbovespa.com.br",
    "Connection": "keep-alive",
}


def criar_sessao() -> requests.Session:
    session = requests.Session()

    retry = Retry(
        total=2,
        connect=2,
        read=2,
        status=2,
        backoff_factor=1.2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )

    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    return session


def carregar_fundos(caminho_csv: str):
    """
    O CSV da B3/Fundos listados vem assim:
    Razão Social;Fundo;Código
    mas cada linha termina com ;, então tratamos com segurança.
    """
    fundos = []

    with open(caminho_csv, "r", encoding="latin1", newline="") as f:
        reader = csv.reader(f, delimiter=";")
        header = next(reader, None)

        for row in reader:
            if not row:
                continue

            # linhas vêm como: razao;fundo;codigo;
            razao = row[0].strip() if len(row) > 0 else ""
            fundo = row[1].strip() if len(row) > 1 else ""
            codigo = row[2].strip() if len(row) > 2 else ""

            if razao or fundo or codigo:
                fundos.append(
                    {
                        "razao_social": razao,
                        "fundo": fundo,
                        "codigo": codigo,
                    }
                )

    return fundos


def localizar_fundo(fundos, termo: str):
    termo_norm = termo.strip().upper()

    candidatos = []

    for fundo in fundos:
        razao = fundo["razao_social"].upper()
        nome_curto = fundo["fundo"].upper()
        codigo = fundo["codigo"].upper()

        if termo_norm in {codigo, nome_curto, razao}:
            candidatos.insert(0, fundo)
        elif termo_norm in codigo or termo_norm in nome_curto or termo_norm in razao:
            candidatos.append(fundo)

    return candidatos


def tentar_json(response: requests.Response):
    try:
        return response.json()
    except ValueError:
        return None


def buscar_fnet(session, descricao, params):
    print("\n" + "=" * 80)
    print(descricao)
    print("Parâmetros:")
    print(json.dumps(params, ensure_ascii=False, indent=2))

    inicio = time.time()

    try:
        response = session.get(
            BASE,
            params=params,
            headers=HEADERS,
            timeout=(5, 20),
        )

        tempo = time.time() - inicio
        print(f"Status: {response.status_code}")
        print(f"Tempo: {tempo:.2f}s")
        print("URL:", response.url)

        data = tentar_json(response)

        if response.status_code != 200:
            if data is not None:
                print(json.dumps(data, ensure_ascii=False, indent=2)[:3000])
            else:
                print(response.text[:1500])
            return None

        if data is None:
            print("Resposta não veio em JSON.")
            print(response.text[:1500])
            return None

        print("Chaves:", list(data.keys()))
        print("recordsTotal:", data.get("recordsTotal"))
        print("recordsFiltered:", data.get("recordsFiltered"))

        registros = data.get("data") or []

        print("Registros retornados:", len(registros))

        for i, item in enumerate(registros[:5], start=1):
            print("\nRegistro", i)
            print("id:", item.get("id"))
            print("descricaoFundo:", item.get("descricaoFundo"))
            print("tipoDocumento:", item.get("tipoDocumento"))
            print("dataReferencia:", item.get("dataReferencia"))
            print("dataEntrega:", item.get("dataEntrega"))
            print("nomePregao:", item.get("nomePregao"))
            print("codSegNegociacao:", item.get("codSegNegociacao"))
            print("cnpjFundo:", item.get("cnpjFundo"))

        return data

    except requests.exceptions.RequestException as e:
        print("Erro de requisição:", e)
        return None


def main():
    termo = sys.argv[1] if len(sys.argv) > 1 else "KNRI"

    fundos = carregar_fundos(CSV_FUNDOS)
    print(f"Fundos carregados do CSV: {len(fundos)}")

    candidatos = localizar_fundo(fundos, termo)

    if not candidatos:
        print(f"Nenhum fundo encontrado no CSV para: {termo}")
        print("Exemplo de uso:")
        print("python teste_fnet_por_fundo_listado.py KNRI")
        return

    escolhido = candidatos[0]

    print("\nFundo escolhido pelo CSV:")
    print(json.dumps(escolhido, ensure_ascii=False, indent=2))

    codigo = escolhido["codigo"]
    fundo_curto = escolhido["fundo"]
    razao_social = escolhido["razao_social"]

    session = criar_sessao()

    # idTipoDocumento 40 = Informe Mensal Estruturado
    # idTipoDocumento 41 = Informe Trimestral Estruturado
    base_params = {
        "d": 1,
        "s": 0,
        "l": 10,
        "tipoFundo": "1",
        "idCategoriaDocumento": "6",
        "idEspecieDocumento": "0",
        "paginaCertificados": "false",
    }

    testes = [
        (
            f"Busca por palavraChave = código {codigo} / Informe Mensal",
            {
                **base_params,
                "idTipoDocumento": "40",
                "palavraChave": codigo,
            },
        ),
        (
            f"Busca por palavraChave = fundo curto {fundo_curto} / Informe Mensal",
            {
                **base_params,
                "idTipoDocumento": "40",
                "palavraChave": fundo_curto,
            },
        ),
        (
            f"Busca por palavraChave = razão social / Informe Mensal",
            {
                **base_params,
                "idTipoDocumento": "40",
                "palavraChave": razao_social,
            },
        ),
        (
            f"Busca por palavraChave = código {codigo} / Informe Trimestral",
            {
                **base_params,
                "idTipoDocumento": "41",
                "palavraChave": codigo,
            },
        ),
        (
            f"Busca por search[value] = código {codigo} / Informe Mensal",
            {
                **base_params,
                "idTipoDocumento": "40",
                "search[value]": codigo,
                "search[regex]": "false",
            },
        ),
        (
            f"Busca por search[value] = razão social / Informe Mensal",
            {
                **base_params,
                "idTipoDocumento": "40",
                "search[value]": razao_social,
                "search[regex]": "false",
            },
        ),
    ]

    for descricao, params in testes:
        buscar_fnet(session, descricao, params)
        time.sleep(1.2)


if __name__ == "__main__":
    main()
