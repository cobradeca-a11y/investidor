from __future__ import annotations

from processamento import analise_qualitativa as aq


def test_fingerprint_analise_muda_quando_indicador_muda():
    base = {"pvp": 0.9, "dy_12m": 0.1, "vacancia_fisica": 1.0, "liquidez_diaria": 10000}
    fii = {"segmento": "LOGISTICA", "nome": "Fundo"}

    fp1 = aq._fingerprint_analise("HGLG11", base, fii, "ctx")
    fp2 = aq._fingerprint_analise("HGLG11", {**base, "pvp": 0.91}, fii, "ctx")

    assert fp1 != fp2


def test_cache_ia_retorna_payload_e_marca_cache(monkeypatch):
    memoria = {}

    def fake_executar(sql, params=()):
        if "INSERT OR REPLACE INTO analise_qualitativa_cache" in sql:
            memoria[(params[0], params[1])] = {
                "payload_json": params[2],
                "criado_em": params[5],
            }

    def fake_buscar_um(sql, params=()):
        return memoria.get((params[0], params[1]))

    monkeypatch.setattr(aq.db, "executar", fake_executar)
    monkeypatch.setattr(aq.db, "buscar_um", fake_buscar_um)

    payload = {"status": "OK", "score": 7, "fonte_qualitativa": "noticias_portal"}
    aq._salvar_cache_ia("KORE11", "abc", payload)
    cached = aq._ler_cache_ia("KORE11", "abc")

    assert cached["score"] == 7
    assert cached["cache_qualitativo"] is True
