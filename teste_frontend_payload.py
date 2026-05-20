"""
teste_frontend_payload.py

Teste estático do dashboard de auditoria na PWA.
Garante que o frontend possui normalização defensiva e renderização dos campos
críticos sem alterar payload/cálculo no backend.
"""
from __future__ import annotations

from pathlib import Path


APP_JS = Path("static/app.js")
STYLE_CSS = Path("static/style.css")


def test_frontend_tem_normalizacao_defensiva_de_auditoria():
    conteudo = APP_JS.read_text(encoding="utf-8")

    assert "function normalizarAuditoria" in conteudo
    assert "function normalizarGatesDetalhes" in conteudo
    assert "function renderAuditoria" in conteudo
    assert "function renderGateDetalhes" in conteudo
    assert "textoSeguro" in conteudo
    assert "asArray" in conteudo
    assert "asObject" in conteudo


def test_frontend_renderiza_campos_auditaveis_criticos():
    conteudo = APP_JS.read_text(encoding="utf-8")

    campos = [
        "payload_hash",
        "payload_hash_calculado",
        "hash_valido",
        "contexto_versao",
        "versao_motor",
        "fonte_patrimonial",
        "score_confianca_dados",
        "nivel_uso_dados",
        "permitir_decisao",
        "campos_ausentes",
        "campos_vencidos",
        "fontes_falharam",
        "gates_detalhes",
        "divergencia_replay",
    ]
    for campo in campos:
        assert campo in conteudo


def test_frontend_mantem_cards_bloqueados_e_gates_visiveis():
    conteudo = APP_JS.read_text(encoding="utf-8")

    assert "card-bloqueado" in conteudo
    assert "Bloqueios/falhas" in conteudo
    assert "gates_detalhes" in conteudo
    assert "Detalhamento de gates não informado" in conteudo
    assert "Não informado" in conteudo


def test_frontend_tem_fluxo_guiado_para_api_key():
    conteudo = APP_JS.read_text(encoding="utf-8")

    assert "function obterOuSolicitarApiKey" in conteudo
    assert "localStorage.setItem('fiia_api_key'" in conteudo
    assert "Configurar chave" in conteudo
    assert "obterOuSolicitarApiKey('ligar o radar')" in conteudo


def test_css_contem_classes_do_dashboard_de_auditoria():
    conteudo = STYLE_CSS.read_text(encoding="utf-8")

    classes = [
        ".audit-panel",
        ".audit-grid",
        ".audit-blocks",
        ".audit-gates-list",
        ".audit-gate",
        ".gate-aprovado",
        ".gate-eliminado",
        ".audit-empty",
        ".card-bloqueado",
    ]
    for classe in classes:
        assert classe in conteudo
