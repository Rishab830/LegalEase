# app/utils/crypto.py
import os
from cryptography.fernet import Fernet, InvalidToken

def get_fernet():
    key = os.environ.get("DOCUMENT_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("DOCUMENT_ENCRYPTION_KEY is not set in the environment.")
    return Fernet(key.encode())

def encrypt_text(plaintext: str) -> str:
    """Encrypt a UTF-8 string. Skips if already encrypted."""
    if is_encrypted(plaintext):
        return plaintext  # Already encrypted, don't double-wrap
    f = get_fernet()
    return f.encrypt(plaintext.encode("utf-8")).decode("utf-8")

def is_encrypted(value: str) -> bool:
    """Check if a string looks like a Fernet token (starts with gAAA)."""
    return isinstance(value, str) and value.startswith("gAAA")

def decrypt_text(token: str) -> str:
    """
    Decrypt a Fernet token. If the value is plaintext (legacy, pre-encryption),
    return it as-is so old documents continue to work.
    """
    if not is_encrypted(token):
        return token  # Already plaintext — legacy document, pass through
    f = get_fernet()
    try:
        return f.decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        raise ValueError("Decryption failed — data is corrupted or the key is wrong.")