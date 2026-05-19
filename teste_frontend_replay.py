"""
teste_frontend_replay.py

Testes estáticos do dashboard de histórico/replay.
Não executa frontend, não chama API, não dispara scraping e não recalcula hash.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP_JS = ROOT / "static" / "app.js"
STYLE_CSS = ROOT / "static" / "style.css"


def _ler(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_dashboard_tem_painel_historico_e_replay():
    js = _ler(APP_JS)

    assert "criarPainelHistorico" in js
    assert "historicoDecisoes" in js
    assert "Histórico e Replay" in js
    assert "carregarHistoricoDecisoes" in js
    assert "consultarDetalheHistorico" in js
    assert "renderDetalheHistorico" in js


def test_historico_consulta_endpoint_auditavel_sem_replay_por_padrao():
    js = _ler(APP_JS)

    assert "/api/auditoria/decisoes/auditaveis?limite=30" in js
    assert "Consulta auditável de decisões salvas" in js
    assert "histórico sem replay" in js.lower() or "sem replay" in js.lower()
    assert "replay=false" in js


def test_replay_so_e_explicito_por_botao():
    js = _ler(APP_JS)

    assert "data-decisao-replay" in js
    assert "Executar replay" in js
    assert "consultarDetalheHistorico(btn.dataset.decisaoReplay, true)" in js
    assert "consultarDetalheHistorico(btn.dataset.decisaoDetalhe, false)" in js
    assert "replay=${replayExplicito ? 'true' : 'false'}" in js
    assert "Replay solicitado" in js


def test_ui_tolera_ausencia_de_replay():
    js = _ler(APP_JS)

    assert "const replay = data.replay || { executado: false }" in js
    assert "Não executado" in js
    assert "Fonte replay" in js
    assert "Não informado" in js


def test_frontend_nao_recalcula_hash_no_replay():
    js = _ler(APP_JS)

    assert "resumirHash" in js
    assert "Hash salvo" in js
    assert "crypto.subtle" not in js
    assert "SHA-256" not in js
    assert "digest(" not in js


def test_historico_usa_autenticacao_existente():
    js = _ler(APP_JS)

    assert "fiia_api_key" in js
    assert "headersAutenticados" in js
    assert "X-API-Key" in js
    assert "Configure <strong>fiia_api_key</strong>" in js


def test_css_tem_estilos_historico_replay():
    css = _ler(STYLE_CSS)

    assert ".history-panel" in css
    assert ".history-header" in css
    assert ".history-list" in css
    assert ".history-row" in css
    assert ".history-actions" in css
    assert ".btn-mini.replay" in css
    assert ".history-detail-panel" in css
