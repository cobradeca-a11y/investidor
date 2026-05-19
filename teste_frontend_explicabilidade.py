"""
teste_frontend_explicabilidade.py

Testes estáticos da UX de explicabilidade da decisão.
Não executa frontend, não chama API, não altera payload e não recalcula hash.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP_JS = ROOT / "static" / "app.js"
STYLE_CSS = ROOT / "static" / "style.css"


def _ler(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_frontend_exibe_explicabilidade_sem_recalcular_hash():
    js = _ler(APP_JS)

    assert "renderResumoExplicabilidade" in js
    assert "renderAuditoria" in js
    assert "Hash e payload auditável são apenas exibidos" in js
    assert "resumirHash" in js
    assert "payload_hash" in js
    assert "crypto.subtle" not in js
    assert "SHA-256" not in js
    assert "digest(" not in js


def test_frontend_renderiza_campos_ausentes_com_fallback():
    js = _ler(APP_JS)

    assert "textoSeguro" in js
    assert "numeroSeguro" in js
    assert "moeda" in js
    assert "percentual" in js
    assert "Não informado" in js
    assert "Detalhamento de gates não informado" in js


def test_frontend_mantem_cards_bloqueados_visiveis():
    js = _ler(APP_JS)
    css = _ler(STYLE_CSS)

    assert "card-bloqueado" in js
    assert "fii.auditoria.permitir_decisao === false" in js
    assert "normalizarClasse(fii.decisao).includes('bloqueado')" in js
    assert ".fii-card.card-bloqueado" in css
    assert "Bloqueado / cautela" in js


def test_frontend_exibe_gates_detalhes_fontes_motivos_metricas():
    js = _ler(APP_JS)

    assert "normalizarGatesDetalhes" in js
    assert "gates_detalhes" in js
    assert "renderGateDetalhes" in js
    assert "Motivos" in js
    assert "Fontes" in js
    assert "Métricas" in js
    assert "Penalidades" in js
    assert "gate-aprovado" in js
    assert "gate-eliminado" in js


def test_frontend_nao_altera_payload_api():
    js = _ler(APP_JS)

    assert "fetch('/api/radar')" in js
    assert "fetch('/api/carteira/posicoes'" in js
    assert "data.oportunidades || []" in js
    assert "data.posicoes" in js
    assert "normalizarFii(raw || {})" in js
    assert "payload.gates_detalhes" in js
    assert "payload_hash_calculado" in js


def test_css_tem_blocos_de_explicabilidade_e_auditoria():
    css = _ler(STYLE_CSS)

    assert ".explain-summary" in css
    assert ".explain-blocked" in css
    assert ".explain-reason" in css
    assert ".audit-note" in css
    assert ".audit-chip" in css
    assert ".audit-chip.danger" in css
    assert ".audit-chip.penalty" in css
    assert ".audit-metric" in css
    assert ".gate-neutro" in css
