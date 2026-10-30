"""Encrypted vault file format.

The vault is a single JSON file:
    {
      "format": "vaultnotes", "version": 1,
      "kdf": {"name": "scrypt", "n": ..., "r": ..., "p": ..., "salt": <b64>},
      "nonce": <b64>, "data": <b64 AES-256-GCM ciphertext>
    }

The key is derived from the master password with scrypt, and the item list
is encrypted with AES-256-GCM, which also detects tampering or a wrong password.
"""

import base64
import json
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

FORMAT = "vaultnotes"
VERSION = 1
AAD = b"vaultnotes-v1"

# scrypt cost: ~128 MB of memory, well under a second on a modern PC.
SCRYPT_N = 2**17
SCRYPT_R = 8
SCRYPT_P = 1


class WrongPassword(Exception):
    pass


class CorruptVault(Exception):
    pass


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"))


def derive_key(password: str, salt: bytes, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P) -> bytes:
    kdf = Scrypt(salt=salt, length=32, n=n, r=r, p=p)
    return kdf.derive(password.encode("utf-8"))


class KeyInfo:
    """A derived key plus the parameters needed to store it in the file header."""

    def __init__(self, key: bytes, salt: bytes, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P):
        self.key = key
        self.salt = salt
        self.n, self.r, self.p = n, r, p

    @classmethod
    def new(cls, password: str) -> "KeyInfo":
        salt = os.urandom(16)
        return cls(derive_key(password, salt), salt)


def encrypt(payload: dict, info: KeyInfo) -> bytes:
    nonce = os.urandom(12)
    plaintext = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    ciphertext = AESGCM(info.key).encrypt(nonce, plaintext, AAD)
    doc = {
        "format": FORMAT,
        "version": VERSION,
        "kdf": {"name": "scrypt", "n": info.n, "r": info.r, "p": info.p, "salt": _b64(info.salt)},
        "nonce": _b64(nonce),
        "data": _b64(ciphertext),
    }
    return json.dumps(doc, indent=1).encode("utf-8")


def decrypt(raw: bytes, password: str) -> tuple[dict, KeyInfo]:
    try:
        doc = json.loads(raw.decode("utf-8"))
        if doc.get("format") != FORMAT:
            raise CorruptVault("Not a Vault Notes file")
        kdf = doc["kdf"]
        salt = _unb64(kdf["salt"])
        n, r, p = int(kdf["n"]), int(kdf["r"]), int(kdf["p"])
        nonce = _unb64(doc["nonce"])
        ciphertext = _unb64(doc["data"])
    except CorruptVault:
        raise
    except Exception as exc:
        raise CorruptVault(f"Vault file is damaged: {exc}") from exc

    key = derive_key(password, salt, n, r, p)
    try:
        plaintext = AESGCM(key).decrypt(nonce, ciphertext, AAD)
    except InvalidTag:
        raise WrongPassword("Wrong master password")
    return json.loads(plaintext.decode("utf-8")), KeyInfo(key, salt, n, r, p)
