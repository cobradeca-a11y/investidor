"""
acesso/rate_limit.py

Rate limit operacional configurável para proteger endpoints sensíveis.

Características:
- desligado por padrão em dev/testes;
- armazenamento simples em memória;
- logs estruturados sem IP completo, API key ou segredo;
- falha fechada apenas quando limite configurado é excedido.
"""
from __future__ import annotations

import hashlib
import time
from collections import defaultdict, deque
from typing import Deque

from fastapi import Header, HTTPException, Request

from config import settings
from sistema import observabilidade

_BUCKETS: dict[str, Deque[float]] = defaultdict(deque)


def limpar_rate_limit() -> None:
    """Limpa estado em memória. Uso previsto em testes."""
    _BUCKETS.clear()


def rate_limit_ativo() -> bool:
    return bool(getattr(settings, "RATE_LIMIT_ENABLED", False))


def _janela_segundos() -> int:
    return max(1, int(getattr(settings, "RATE_LIMIT_WINDOW_SECONDS", 60)))


def _hash_identificador(valor: str) -> str:
    return hashlib.sha256(valor.encode("utf-8")).hexdigest()[:16]


def _identificador_cliente(request: Request | None, x_api_key: str | None = None) -> str:
    """
    Identifica cliente sem armazenar segredo.

    Prioridade:
    - hash da API key, quando existir;
    - hash do IP; 
    - identificador anônimo.
    """
    if x_api_key:
        return f"key:{_hash_identificador(str(x_api_key))}"
    ip = "anonimo"
    if request is not None and getattr(request, "client", None):
        ip = request.client.host or "anonimo"
    return f"ip:{_hash_identificador(ip)}"


def _limite_por_escopo(escopo: str, limite: int | None = None) -> int:
    if limite is not None:
        return max(1, int(limite))
    if escopo == "radar":
        return max(1, int(getattr(settings, "RATE_LIMIT_RADAR_MAX", 3)))
    if escopo == "sensivel":
        return max(1, int(getattr(settings, "RATE_LIMIT_SENSITIVE_MAX", 30)))
    return max(1, int(getattr(settings, "RATE_LIMIT_DEFAULT_MAX", 120)))


def verificar_rate_limit(
    request: Request | None = None,
    *,
    escopo: str = "default",
    limite: int | None = None,
    x_api_key: str | None = Header(None),
) -> None:
    """
    Verifica rate limit para endpoint.

    Quando RATE_LIMIT_ENABLED=False, retorna no-op para não bloquear testes locais.
    """
    if not rate_limit_ativo():
        return

    agora = time.monotonic()
    janela = _janela_segundos()
    maximo = _limite_por_escopo(escopo, limite)
    cliente = _identificador_cliente(request, x_api_key=x_api_key)
    chave_bucket = f"{escopo}:{cliente}"
    bucket = _BUCKETS[chave_bucket]

    while bucket and agora - bucket[0] >= janela:
        bucket.popleft()

    if len(bucket) >= maximo:
        observabilidade.registrar_evento(
            "WARN",
            "acesso.rate_limit",
            "Rate limit excedido",
            contexto={
                "escopo": escopo,
                "cliente_hash": cliente,
                "limite": maximo,
                "janela_segundos": janela,
                "tentativas_na_janela": len(bucket),
            },
        )
        raise HTTPException(status_code=429, detail="Muitas requisições. Tente novamente mais tarde.")

    bucket.append(agora)


def dependencia_rate_limit(escopo: str = "default", limite: int | None = None):
    """Factory para uso com Depends em FastAPI."""
    def _dependencia(request: Request, x_api_key: str | None = Header(None)) -> None:
        verificar_rate_limit(request, escopo=escopo, limite=limite, x_api_key=x_api_key)
    return _dependencia
