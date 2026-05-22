"""
acesso/auth.py
Autenticação local por senha com hash SHA-256.
A senha nunca é armazenada em texto puro.

O hash deve ser definido via variável de ambiente FIIA_SENHA_HASH no .env.
Para gerar o hash da sua senha:
    python -c "import hashlib; print(hashlib.sha256(b'sua_senha').hexdigest())"
"""
import hashlib
import getpass
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

_CONFIG_PATH = Path.home() / ".fiia_config"
_HASH_CORRETO = os.getenv("FIIA_SENHA_HASH", "")


def _hash(senha: str) -> str:
    return hashlib.sha256(senha.encode()).hexdigest()


def autenticar() -> bool:
    """
    Solicita a senha no terminal e valida contra o hash.
    Retorna True se autenticado, False caso contrário.
    """
    if not _HASH_CORRETO:
        print("⚠️  FIIA_SENHA_HASH não configurada no .env. Acesso bloqueado.")
        print("   Gere o hash com: python -c \"import hashlib; print(hashlib.sha256(b'sua_senha').hexdigest())\"")
        print("   E adicione FIIA_SENHA_HASH=<hash> ao seu .env")
        return False

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
