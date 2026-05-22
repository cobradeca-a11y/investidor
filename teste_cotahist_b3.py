from __future__ import annotations

from coleta import cotahist_b3


def _linha_cotahist(
    ticker: str = "HGLG11",
    data: str = "20210520",
    preco_fechamento: int = 15495,
    volume: int = 123456789,
) -> str:
    linha = list(" " * 245)

    def put(inicio: int, fim: int, valor: str) -> None:
        texto = str(valor).ljust(fim - inicio)
        linha[inicio:fim] = list(texto[: fim - inicio])

    def put_num(inicio: int, fim: int, valor: int) -> None:
        texto = str(valor).zfill(fim - inicio)
        linha[inicio:fim] = list(texto)

    put(0, 2, "01")
    put(2, 10, data)
    put(10, 12, "12")
    put(12, 24, ticker)
    put(24, 27, "010")
    put_num(56, 69, 15000)
    put_num(69, 82, 15600)
    put_num(82, 95, 14950)
    put_num(95, 108, 15300)
    put_num(108, 121, preco_fechamento)
    put_num(147, 152, 123)
    put_num(152, 170, 4567)
    put_num(170, 188, volume)
    return "".join(linha)


def test_parse_linha_cotahist_fii_a_vista():
    registro = cotahist_b3.parse_linha(_linha_cotahist(), arquivo_origem="COTAHIST_A2021.TXT")

    assert registro is not None
    assert registro["ticker"] == "HGLG11"
    assert registro["data"] == "2021-05-20"
    assert registro["tipo_mercado"] == "010"
    assert registro["preco_fechamento"] == 154.95
    assert registro["volume_financeiro"] == 1234567.89


def test_parse_linha_ignora_mercado_diferente_de_vista():
    linha = _linha_cotahist()
    linha = linha[:24] + "020" + linha[27:]

    assert cotahist_b3.parse_linha(linha) is None


def test_parse_linha_ignora_ticker_nao_fii():
    assert cotahist_b3.parse_linha(_linha_cotahist(ticker="PETR4")) is None
