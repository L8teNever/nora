from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


class EncryptionError(RuntimeError):
    pass


def _fernet() -> Fernet:
    key = get_settings().nora_encryption_key.strip()
    if not key:
        raise EncryptionError(
            "NORA_ENCRYPTION_KEY is not set. Generate one with: "
            "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception as exc:
        raise EncryptionError("NORA_ENCRYPTION_KEY is not a valid Fernet key") from exc


def encrypt_secret(plaintext: str) -> str:
    if not plaintext:
        return ""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    if not ciphertext:
        return ""
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise EncryptionError("Could not decrypt stored token (wrong NORA_ENCRYPTION_KEY?)") from exc
