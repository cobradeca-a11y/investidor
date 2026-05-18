"""
processamento/nlp_fnet.py
Classificação NLP de documentos FNET com Gemini.

Objetivo:
- ler conteúdo real quando disponível;
- classificar risco operacional/documental por IA;
- manter cache por hash para não reprocessar o mesmo documento;
- retornar fallback seguro quando não houver texto ou chave Gemini.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from google import genai

from banco import db
from config import settings
from sistema import observabilidade

TABELA = "fnet_nlp_classificacoes"


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def garantir_tabela() -> None:
    db.executar(
        f"""
        CREATE TABLE IF NOT EXISTS {TABELA} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            documento_hash TEXT NOT NULL UNIQUE,
            documento_id TEXT,
            ticker TEXT,
            nivel TEXT NOT NULL,
            motivo TEXT,
            termos_detectados TEXT,
            modelo TEXT,
            criado_em TEXT NOT NULL,
            payload_json TEXT
        );
        """
    )


def _hash_documento(texto: str, assunto: str | None = None) -> str:
    base = f"{assunto or ''}\n{texto or ''}".strip().encode("utf-8")
    return hashlib.sha256(base).hexdigest()


def _limpar_json(texto: str) -> dict[str, Any]:
    bruto = texto.strip()
    if "```json" in bruto:
        bruto = bruto.split("```json", 1)[1].split("```", 1)[0]
    elif "```" in bruto:
        bruto = bruto.split("```", 1)[1].split("```", 1)[0]
    bruto = re.sub(r"//.*", "", bruto).strip()
    try:
        return json.loads(bruto)
    except json.JSONDecodeError:
        match = re.search(r"(\{.*\})", bruto, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        raise


def _salvar_cache(documento_hash: str, ticker: str | None, documento_id: Any, resultado: dict[str, Any]) -> None:
    garantir_tabela()
    payload = json.dumps(resultado, ensure_ascii=False, default=str)
    db.executar(
        f"""
        INSERT INTO {TABELA}
            (documento_hash, documento_id, ticker, nivel, motivo, termos_detectados, modelo, criado_em, payload_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(documento_hash)
        DO UPDATE SET
            documento_id=excluded.documento_id,
            ticker=excluded.ticker,
            nivel=excluded.nivel,
            motivo=excluded.motivo,
            termos_detectados=excluded.termos_detectados,
            modelo=excluded.modelo,
            criado_em=excluded.criado_em,
            payload_json=excluded.payload_json
        """,
        (
            documento_hash,
            str(documento_id) if documento_id is not None else None,
            ticker,
            resultado.get("nivel", "INDEFINIDO"),
            resultado.get("motivo"),
            json.dumps(resultado.get("termos_detectados", []), ensure_ascii=False),
            resultado.get("modelo"),
            _agora_iso(),
            payload,
        ),
    )


def _buscar_cache(documento_hash: str) -> dict[str, Any] | None:
    garantir_tabela()
    row = db.buscar_um(f"SELECT payload_json FROM {TABELA} WHERE documento_hash = ?", (documento_hash,))
    if not row or not row["payload_json"]:
        return None
    try:
        payload = json.loads(row["payload_json"])
        payload["cache"] = True
        return payload
    except Exception:
        return None


def classificar_documento_com_ia(
    texto_documento: str,
    assunto: str = "",
    ticker: str | None = None,
    documento_id: Any = None,
) -> dict[str, Any]:
    """Classifica documento FNET por conteúdo real usando Gemini."""
    texto = (texto_documento or "").strip()
    if len(texto) < 80:
        return {
            "nivel": "INDEFINIDO",
            "motivo": "Texto do documento indisponível ou insuficiente para NLP.",
            "termos_detectados": [],
            "fonte_classificacao": "fallback_sem_texto",
            "cache": False,
        }

    documento_hash = _hash_documento(texto[:12000], assunto)
    cache = _buscar_cache(documento_hash)
    if cache:
        return cache

    if not settings.GEMINI_API_KEY or settings.GEMINI_API_KEY in ("", "SUA_CHAVE_AQUI", "sua_chave_aqui"):
        return {
            "nivel": "INDEFINIDO",
            "motivo": "Gemini indisponível: chave de API não configurada.",
            "termos_detectados": [],
            "fonte_classificacao": "fallback_sem_gemini",
            "cache": False,
        }

    prompt = f"""
Você é um analista sênior de risco para Fundos Imobiliários brasileiros.
Sua tarefa é classificar o RISCO OPERACIONAL/DOCUMENTAL REAL do documento FNET abaixo.

Regra principal:
NÃO classifique um documento como MEDIO ou ALTO apenas porque ele é relevante, anual, trimestral, extenso, institucional ou consolidado.
Classifique como MEDIO ou ALTO somente se houver sinal explícito de risco, deterioração ou evento material no texto.

Critérios:

- BAIXO:
Documento rotineiro sem deterioração explícita.
Inclui: informe anual normal, informe trimestral normal, informe mensal normal, rendimento recorrente, assembleia comum,
comunicado administrativo, relatório sem alerta material, documentação extensa porém sem sinal objetivo de risco.

- MEDIO:
Evento com potencial impacto moderado na tese.
Inclui: emissão/oferta/subscrição relevante, alteração operacional relevante, queda operacional moderada,
aumento moderado de vacância, renegociação relevante, mudança de gestor/administrador sem crise,
relatório com sinais claros porém não severos de deterioração.

- ALTO:
Evento que altera materialmente a tese ou indica risco severo.
Inclui: inadimplência relevante, default, liquidação, risco jurídico severo, vacância grave, perda estrutural de receita,
renúncia ou destituição crítica, reavaliação patrimonial severa, descumprimento de obrigação, deterioração financeira grave.

Instruções adicionais:
- Se o documento for apenas um informe anual/trimestral padrão e o texto não trouxer alerta explícito, classifique como BAIXO.
- Se você não conseguir apontar o termo ou trecho que prova o risco, não classifique como ALTO.
- Em caso de dúvida entre BAIXO e MEDIO, escolha BAIXO.
- Em caso de dúvida entre MEDIO e ALTO, escolha MEDIO.
- Não confunda importância para análise com risco.

Assunto: {assunto[:500]}
Conteúdo:
{texto[:12000]}

Responda APENAS em JSON puro:
{{
  "nivel": "ALTO|MEDIO|BAIXO",
  "motivo": "explicação objetiva em até 2 frases, citando o sinal de risco real quando existir",
  "termos_detectados": ["termo1", "termo2"]
}}
"""

    try:
        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        modelo = "gemini-2.5-flash"
        response = client.models.generate_content(model=modelo, contents=prompt)
        data = _limpar_json(response.text)
        nivel = str(data.get("nivel", "INDEFINIDO")).upper()
        if nivel not in {"ALTO", "MEDIO", "BAIXO"}:
            nivel = "INDEFINIDO"
        resultado = {
            "nivel": nivel,
            "motivo": data.get("motivo") or "Classificação sem motivo detalhado.",
            "termos_detectados": data.get("termos_detectados") or [],
            "fonte_classificacao": "gemini_fnet_pdf",
            "modelo": modelo,
            "documento_hash": documento_hash,
            "cache": False,
        }
        _salvar_cache(documento_hash, ticker, documento_id, resultado)
        return resultado
    except Exception as erro:
        observabilidade.registrar_erro(
            "processamento.nlp_fnet",
            erro,
            ticker=ticker,
            contexto={"documento_id": documento_id, "assunto": assunto[:200]},
        )
        return {
            "nivel": "INDEFINIDO",
            "motivo": f"Erro ao classificar documento por IA: {str(erro)[:160]}",
            "termos_detectados": [],
            "fonte_classificacao": "erro_gemini",
            "cache": False,
        }
