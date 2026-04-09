"""
Fernet symmetric encryption helpers.
Used by the EncryptedText SQLAlchemy TypeDecorator for at-rest encryption of
sensitive fields (password_hash, payout identifiers).

Key rotation:
  Place additional key files alongside the primary key in the same directory.
  All *.key files are loaded; the primary key (FERNET_KEY_PATH) is used for
  new encryptions. All keys (primary + extras) are tried on decryption via
  MultiFernet, so old ciphertexts remain readable after a key rotation.

  Rotation workflow:
    1. Generate a new key: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    2. Write the new key to data/keys/secret.key (old key moves to e.g. data/keys/secret.key.old)
    3. Restart the app — new writes use the new key; old ciphertexts still decrypt.
    4. Re-encrypt existing rows at your leisure and remove the old key file.
"""
import os
import glob as _glob
from cryptography.fernet import Fernet, MultiFernet

_fernet: MultiFernet | None = None


def init_fernet(key_path: str) -> None:
    """Load the primary key and any additional *.key files from the same directory."""
    global _fernet
    key_dir = os.path.dirname(key_path) or "."
    os.makedirs(key_dir, exist_ok=True)
    if not os.path.exists(key_path):
        with open(key_path, "wb") as f:
            f.write(Fernet.generate_key())

    # Primary key first (used for encryption); extras sorted by mtime descending
    primary_key = _read_key(key_path)
    extra_paths = sorted(
        [p for p in _glob.glob(os.path.join(key_dir, "*.key")) if p != key_path],
        key=os.path.getmtime,
        reverse=True,
    )
    keys = [primary_key] + [_read_key(p) for p in extra_paths]
    _fernet = MultiFernet(keys)


def _read_key(path: str) -> Fernet:
    with open(path, "rb") as f:
        return Fernet(f.read().strip())


def encrypt(plaintext: str) -> str:
    if _fernet is None:
        raise RuntimeError("Fernet not initialised — call init_fernet() first")
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    if _fernet is None:
        raise RuntimeError("Fernet not initialised — call init_fernet() first")
    return _fernet.decrypt(ciphertext.encode()).decode()
