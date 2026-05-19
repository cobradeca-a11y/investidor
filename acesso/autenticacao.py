"""
acesso/autenticacao.py

Dependencias de autenticacao para endpoints sensiveis.
"""
from __future__ import annotations

import secrets

from fastapi import Header, HTTPException

from config.settings import FIIA_API_KEY


def verificar_api_key(x_api_key: str | None = Header(None)) -> None:
    """Valida a chave da API em modo fail-closed."""
    if not FIIA_API_KEY:
        raise HTTPException(status_code=500, detail="FIIA_API_KEY nao configurada")
    if not x_api_key or not secrets.compare_digest(x_api_key, FIIA_API_KEY):
        raise HTTPException(status_code=401, detail="API Key invalida ou ausente")
