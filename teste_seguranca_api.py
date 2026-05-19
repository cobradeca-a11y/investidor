"""
teste_seguranca_api.py

Valida hardening de segurança sem disparar scraping ou motor decisório.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from acesso import seguranca
from api import auditoria as api_auditoria
from config import settings


def test_api_key_fail_closed_sem_chave_configurada(monkeypatch):
    monkeypatch.setattr(settings, "FIIA_API_KEY", "")
    monkeypatch.setattr(settings, "FIIA_ENV", "dev")

    with pytest.raises(HTTPException) as exc:
        seguranca.verificar_api_key("qualquer")

    assert exc.value.status_code == 500
    assert "Autenticação" in exc.value.detail
    assert "qualquer" not in exc.value.detail


def test_api_key_rejeita_ausente_ou_incorreta_sem_vazar_segredo(monkeypatch):
    monkeypatch.setattr(settings, "FIIA_API_KEY", "chave-local-forte-com-mais-de-24-caracteres")
    monkeypatch.setattr(settings, "FIIA_ENV", "dev")

    with pytest.raises(HTTPException) as ausente:
        seguranca.verificar_api_key(None)
    with pytest.raises(HTTPException) as incorreta:
        seguranca.verificar_api_key("errada")

    assert ausente.value.status_code == 401
    assert incorreta.value.status_code == 401
    assert "chave-local-forte" not in ausente.value.detail
    assert "chave-local-forte" not in incorreta.value.detail
    assert "errada" not in incorreta.value.detail


def test_api_key_aceita_chave_valida_em_dev(monkeypatch):
    chave = "chave-local-forte-com-mais-de-24-caracteres"
    monkeypatch.setattr(settings, "FIIA_API_KEY", chave)
    monkeypatch.setattr(settings, "FIIA_ENV", "dev")

    assert seguranca.verificar_api_key(chave) is None


def test_producao_rejeita_chave_padrao(monkeypatch):
    monkeypatch.setattr(settings, "FIIA_ENV", "prod")
    monkeypatch.setattr(settings, "FIIA_API_KEY", "ci-fiia-key")

    with pytest.raises(HTTPException) as exc:
        seguranca.verificar_api_key("ci-fiia-key")

    assert exc.value.status_code == 500
    assert "produção" in exc.value.detail.lower()
    assert "ci-fiia-key" not in exc.value.detail


def test_producao_rejeita_chave_curta(monkeypatch):
    monkeypatch.setattr(settings, "FIIA_ENV", "production")
    monkeypatch.setattr(settings, "FIIA_API_KEY", "curta")

    with pytest.raises(HTTPException) as exc:
        seguranca.verificar_api_key("curta")

    assert exc.value.status_code == 500
    assert "curta" not in exc.value.detail


def test_producao_aceita_chave_forte(monkeypatch):
    chave = "prod-chave-super-forte-1234567890"
    monkeypatch.setattr(settings, "FIIA_ENV", "prod")
    monkeypatch.setattr(settings, "FIIA_API_KEY", chave)

    assert seguranca.verificar_api_key(chave) is None


def test_validar_configuracao_seguranca_nao_expoe_segredo(monkeypatch):
    monkeypatch.setattr(settings, "FIIA_ENV", "prod")
    monkeypatch.setattr(settings, "FIIA_API_KEY", "segredo-curto")
    monkeypatch.setattr(settings, "FIIA_DEBUG", True)

    resultado = settings.validar_configuracao_seguranca()

    assert resultado["seguro"] is False
    assert "segredo-curto" not in str(resultado)
    assert any("produção" in item.lower() for item in resultado["problemas"])


def test_resposta_erro_segura_nao_tem_stacktrace():
    resposta = seguranca.resposta_erro_segura("Falha controlada.", detalhe="sem segredo")

    assert resposta["status"] == "erro"
    assert resposta["mensagem"] == "Falha controlada."
    assert "traceback" not in str(resposta).lower()


def test_headers_seguranca_defensivos():
    headers = seguranca.cabecalhos_seguranca()

    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Referrer-Policy"] == "no-referrer"
    assert headers["Cache-Control"] == "no-store"


def test_api_auditoria_usa_autenticacao_central():
    assert api_auditoria.verificar_api_key is seguranca.verificar_api_key


def test_api_auditoria_erro_controlado_sem_stacktrace(monkeypatch):
    def falhar(*args, **kwargs):
        raise RuntimeError("segredo interno sensivel")

    monkeypatch.setattr(api_auditoria, "listar_decisoes_auditaveis", falhar)
    monkeypatch.setattr(api_auditoria.observabilidade, "registrar_erro", lambda *args, **kwargs: None)

    resposta = api_auditoria.listar_decisoes_auditaveis_api()

    assert resposta["status"] == "erro"
    assert "Falha controlada" in resposta["mensagem"]
    assert "traceback" not in str(resposta).lower()
    assert "segredo interno sensivel" not in str(resposta)
