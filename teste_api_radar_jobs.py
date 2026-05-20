from __future__ import annotations

from fastapi.testclient import TestClient

import acesso.autenticacao as auth
import app as app_mod


def _headers():
    return {"x-api-key": auth.FIIA_API_KEY}


def test_radar_jobs_exige_api_key(monkeypatch):
    monkeypatch.setattr(auth, "FIIA_API_KEY", "teste-radar-jobs")
    client = TestClient(app_mod.app)

    resp = client.post("/api/radar/jobs")

    assert resp.status_code == 401


def test_radar_jobs_executa_e_disponibiliza_resultado(monkeypatch):
    monkeypatch.setattr(auth, "FIIA_API_KEY", "teste-radar-jobs")
    monkeypatch.setattr(app_mod, "_RADAR_JOBS", {})
    monkeypatch.setattr(app_mod, "_ULTIMO_RADAR", None)
    monkeypatch.setattr(
        app_mod.estrategia,
        "radar_oportunidades",
        lambda: [{"ticker": "KORE11", "decisao": "MONITORAR"}],
    )
    client = TestClient(app_mod.app)

    inicio = client.post("/api/radar/jobs", headers=_headers())

    assert inicio.status_code == 200
    job_id = inicio.json()["job_id"]

    final = None
    for _ in range(50):
        consulta = client.get(f"/api/radar/jobs/{job_id}", headers=_headers())
        assert consulta.status_code == 200
        final = consulta.json()["job"]
        if final["status"] == "concluido":
            break

    assert final is not None
    assert final["status"] == "concluido"
    assert final["resultado"]["quantidade"] == 1

    ultimo = client.get("/api/radar/ultimo", headers=_headers())
    assert ultimo.status_code == 200
    assert ultimo.json()["oportunidades"][0]["ticker"] == "KORE11"


def test_radar_job_inexistente_retorna_404(monkeypatch):
    monkeypatch.setattr(auth, "FIIA_API_KEY", "teste-radar-jobs")
    client = TestClient(app_mod.app)

    resp = client.get("/api/radar/jobs/nao-existe", headers=_headers())

    assert resp.status_code == 404
