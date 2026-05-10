# app/utils/crypto.py
import os
import base64
from cryptography.fernet import Fernet, InvalidToken

def get_fernet():
    """Load the Fernet cipher from the environment variable."""
    key = os.environ.get("DOCUMENT_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("DOCUMENT_ENCRYPTION_KEY is not set in the environment.")
    return Fernet(key.encode())

def encrypt_text(plaintext: str) -> str:
    """Encrypt a UTF-8 string. Returns a URL-safe base64 token string."""
    f = get_fernet()
    return f.encrypt(plaintext.encode("utf-8")).decode("utf-8")

def decrypt_text(token: str) -> str:
    """Decrypt a Fernet token back to a UTF-8 string."""
    f = get_fernet()
    try:
        return f.decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        raise ValueError("Decryption failed — data may be corrupted or the key is wrong.")