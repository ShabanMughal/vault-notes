import pytest

from vault_notes import crypto
from vault_notes.app import generate_password
from vault_notes.storage import Vault, new_item


@pytest.fixture
def vault(tmp_path):
    v = Vault(tmp_path / "vault.vnx")
    v.create("correct horse")
    item = new_item("login")
    item.update(title="My VPS", username="root", password="s3cret!", url="1.2.3.4")
    v.items.append(item)
    v.save()
    return v


def test_file_is_encrypted(vault):
    raw = vault.path.read_bytes()
    assert b"s3cret" not in raw
    assert b"My VPS" not in raw


def test_unlock_round_trip(vault):
    other = Vault(vault.path)
    other.unlock("correct horse")
    assert other.items[0]["password"] == "s3cret!"


def test_wrong_password_rejected(vault):
    with pytest.raises(crypto.WrongPassword):
        Vault(vault.path).unlock("wrong")


def test_tampered_file_rejected(vault):
    raw = bytearray(vault.path.read_bytes())
    i = raw.index(b'"data": "') + 12
    raw[i] = ord("A") if raw[i] != ord("A") else ord("B")
    vault.path.write_bytes(bytes(raw))
    with pytest.raises((crypto.WrongPassword, crypto.CorruptVault)):
        Vault(vault.path).unlock("correct horse")


def test_change_password(vault):
    vault.change_password("correct horse", "new password")
    Vault(vault.path).unlock("new password")
    with pytest.raises(crypto.WrongPassword):
        Vault(vault.path).unlock("correct horse")


def test_lock_clears_memory(vault):
    vault.lock()
    assert not vault.unlocked
    assert vault.items == []


def test_backup(vault, tmp_path):
    folder = tmp_path / "usb"
    folder.mkdir()
    target = vault.backup_to(folder)
    Vault(target).unlock("correct horse")


def test_generate_password():
    pw = generate_password()
    assert len(pw) == 20
    assert any(c.isupper() for c in pw) and any(c.islower() for c in pw) and any(c.isdigit() for c in pw)
