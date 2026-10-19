"""Chaves de API no cofre do sistema (Keychain, Credential Manager, Secret Service).

Serviço "rtfc", conta = id do provedor ("openai", "tavily"…). As chaves nunca vão para
arquivos de configuração nem para logs, e o backend nunca as devolve para a UI (só se existem).
"""

from typing import Protocol

SERVICE = "rtfc"


class SecretStore(Protocol):
    def get(self, account: str) -> str | None: ...
    def set(self, account: str, value: str) -> None: ...
    def delete(self, account: str) -> None: ...


class KeyringSecretStore:
    def get(self, account: str) -> str | None:
        import keyring

        try:
            return keyring.get_password(SERVICE, account)
        except Exception:
            return None

    def set(self, account: str, value: str) -> None:
        import keyring

        keyring.set_password(SERVICE, account, value)

    def delete(self, account: str) -> None:
        import keyring
        from keyring.errors import PasswordDeleteError

        try:
            keyring.delete_password(SERVICE, account)
        except PasswordDeleteError:
            pass


class MemorySecretStore:
    """Para testes."""

    def __init__(self, initial: dict[str, str] | None = None) -> None:
        self.values = dict(initial or {})

    def get(self, account: str) -> str | None:
        return self.values.get(account)

    def set(self, account: str, value: str) -> None:
        self.values[account] = value

    def delete(self, account: str) -> None:
        self.values.pop(account, None)
