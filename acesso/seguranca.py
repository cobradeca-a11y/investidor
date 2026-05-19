"""
acesso/seguranca.py

Camada central de segurança para endpoints sensíveis do FIIA.

Regras:
- fail-closed quando FIIA_API_KEY não está configurada;
- produção não aceita chave padrão, curta ou insegura;
- mensagens de erro não expõem segredos;
- comparação de chave usa secrets.compare_digest.
"""
from __future__ import annotations

import secrets
from typing import Any

from fastapi import Header, HTTPException, Request
from fastapi.responses import JSONResponse

from config import settings


def cabecalhos_seguranca() -> dict[str, str]:
    """Headers defensivos aplicáveis a respostas HTTP."""
    return {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "Cache-Control": "no-store",
    }


def erro_seguro(status_code: int, mensagem: str) -> HTTPException:
    """Cria erro HTTP sem expor segredo, stacktrace ou configuração interna."""
    return HTTPException(status_code=status_code, detail=mensagem)


def verificar_api_key(x_api_key: str | None = Header(None)) -> None:
    """
    Verifica API key para endpoints sensíveis.

    Fail-closed:
    - sem chave configurada: bloqueia;
    - produção com chave padrão/curta: bloqueia;
    - header ausente/incorreto: bloqueia.
    """
    if not settings.FIIA_API_KEY:
        raise erro_seguro(500, "Autenticação da API não configurada.")

    if settings.ambiente_producao() and settings.api_key_padrao_ou_insegura():
        raise erro_seguro(500, "Configuração de autenticação inválida para produção.")

    if not x_api_key:
        raise erro_seguro(401, "API key ausente ou inválida.")

    if not secrets.compare_digest(str(x_api_key), str(settings.FIIA_API_KEY)):
        raise erro_seguro(401, "API key ausente ou inválida.")


def resposta_erro_segura(mensagem: str, status: str = "erro", **extras: Any) -> dict[str, Any]:
    """Payload de erro sem stacktrace nem detalhes sensíveis."""
    return {"status": status, "mensagem": mensagem, **extras}


async def middleware_headers_seguranca(request: Request, call_next):
    """Middleware opcional para adicionar headers defensivos."""
    try:
        response = await call_next(request)
    except Exception:
        response = JSONResponse(
            status_code=500,
            content=resposta_erro_segura("Falha interna controlada."),
        )
    for chave, valor in cabecalhos_seguranca().items():
        response.headers.setdefault(chave, valor)
    return response
