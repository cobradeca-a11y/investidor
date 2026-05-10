"""
acesso/auth.py
Autenticação local por senha com hash SHA-256.
A senha nunca é armazenada em texto puro.
"""
import hashlib
import getpass
from pathlib import Path

_CONFIG_PATH = Path.home() / ".fiia_config"
_HASH_CORRETO = "6aa81c4b1b739b3e82bbf3a5586aad9ccdd3bbfaa460f53d04b1a34cc542e316"


def _hash(senha: str) -> str:
    return hashlib.sha256(senha.encode()).hexdigest()


def autenticar() -> bool:
    """
    Solicita a senha no terminal e valida contra o hash.
    Retorna True se autenticado, False caso contrário.
    """
    tentativas = 3
    for i in range(tentativas):
        senha = getpass.getpass("🔒 FIIA — Senha de acesso: ")
        if _hash(senha) == _HASH_CORRETO:
            return True
        restantes = tentativas - i - 1
        if restantes > 0:
            print(f"   Senha incorreta. {restantes} tentativa(s) restante(s).")
    print("   Acesso negado.")
    return False


def exigir_autenticacao() -> None:
    """
    Autentica ou encerra o programa.
    Use no início de main.py.
    """
    if not autenticar():
        raise SystemExit(1)
