"""Loading and saving the vault file on disk."""

import os
import shutil
import time
import uuid
from datetime import datetime
from pathlib import Path

from . import crypto


def default_vault_path() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "VaultNotes" / "vault.vnx"


def new_item(kind: str) -> dict:
    now = time.time()
    item = {
        "id": uuid.uuid4().hex,
        "type": kind,  # "note" or "login"
        "title": "",
        "body": "",
        "created": now,
        "updated": now,
    }
    if kind == "login":
        item.update(username="", password="", url="")
    return item


class Vault:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.items: list[dict] = []
        self._key: crypto.KeyInfo | None = None

    @property
    def exists(self) -> bool:
        return self.path.exists()

    @property
    def unlocked(self) -> bool:
        return self._key is not None

    def create(self, password: str) -> None:
        self._key = crypto.KeyInfo.new(password)
        self.items = []
        self.save()

    def unlock(self, password: str) -> None:
        payload, key = crypto.decrypt(self.path.read_bytes(), password)
        self.items = payload.get("items", [])
        self._key = key

    def lock(self) -> None:
        self._key = None
        self.items = []

    def verify_password(self, password: str) -> bool:
        try:
            crypto.decrypt(self.path.read_bytes(), password)
            return True
        except crypto.WrongPassword:
            return False

    def change_password(self, old: str, new: str) -> None:
        crypto.decrypt(self.path.read_bytes(), old)  # raises WrongPassword
        self._key = crypto.KeyInfo.new(new)
        self.save()

    def save(self) -> None:
        if self._key is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = crypto.encrypt({"items": self.items}, self._key)
        # Write to a temp file and swap it in, so a crash never leaves a half-written vault.
        tmp = self.path.with_suffix(".tmp")
        with open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        if self.path.exists():
            shutil.copy2(self.path, self.path.with_suffix(".bak"))
        os.replace(tmp, self.path)

    def backup_to(self, folder: Path) -> Path:
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        target = Path(folder) / f"vault-backup-{stamp}.vnx"
        shutil.copy2(self.path, target)
        return target
