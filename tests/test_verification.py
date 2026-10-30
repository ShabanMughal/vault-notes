import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QLineEdit

from vault_notes import app as appmod
from vault_notes import hello
from vault_notes.storage import Vault


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    vault = Vault(tmp_path / "v.vnx")
    w = appmod.MainWindow(vault, appmod.make_icon())
    w.lock_page.password.setText("masterpass1")
    w.lock_page.confirm.setText("masterpass1")
    w.lock_page.submit()
    w.add_item("login")
    w.main_page.editor.password.setText("hunter2")
    yield w
    w.quitting = True
    w.tray.hide()
    w.close()


def fake_hello(monkeypatch, result):
    calls = []

    def verify(hwnd, reason, on_done):
        calls.append(reason)
        on_done(result)

    monkeypatch.setattr(hello, "verify", verify)
    return calls


def test_reveal_requires_hello(window, monkeypatch):
    calls = fake_hello(monkeypatch, hello.OK)
    ed = window.main_page.editor
    ed.toggle_reveal()
    assert len(calls) == 1
    assert ed.password.echoMode() == QLineEdit.Normal


def test_cancel_keeps_password_hidden(window, monkeypatch):
    fake_hello(monkeypatch, hello.CANCELLED)
    ed = window.main_page.editor
    ed.toggle_reveal()
    assert ed.password.echoMode() == QLineEdit.Password


def test_grace_period_then_forget(window, monkeypatch):
    calls = fake_hello(monkeypatch, hello.OK)
    ed = window.main_page.editor
    ed.toggle_reveal()
    ed.toggle_reveal()  # hide
    ed.toggle_reveal()  # show again within grace period
    assert len(calls) == 1
    window.forget_verification()  # e.g. Windows was locked
    assert ed.password.echoMode() == QLineEdit.Password
    ed.toggle_reveal()
    assert len(calls) == 2


def test_copy_requires_hello(window, monkeypatch):
    copied = []
    monkeypatch.setattr(window, "copy_secret", lambda text, what: copied.append(text))
    fake_hello(monkeypatch, hello.CANCELLED)
    window.main_page.editor.copy_password()
    assert copied == []
    fake_hello(monkeypatch, hello.OK)
    window.main_page.editor.copy_password()
    assert copied == ["hunter2"]


def test_falls_back_to_master_password(window, monkeypatch):
    fake_hello(monkeypatch, hello.UNAVAILABLE)
    monkeypatch.setattr(appmod.MasterPasswordPrompt, "exec", lambda self: 0)
    ed = window.main_page.editor
    ed.toggle_reveal()
    assert ed.password.echoMode() == QLineEdit.Password
    monkeypatch.setattr(appmod.MasterPasswordPrompt, "exec", lambda self: 1)
    ed.toggle_reveal()
    assert ed.password.echoMode() == QLineEdit.Normal


def test_master_password_prompt_checks_password(window):
    dlg = appmod.MasterPasswordPrompt(window, window.vault)
    dlg.password.setText("wrong")
    dlg.submit()
    assert dlg.result() == 0
    dlg.password.setText("masterpass1")
    dlg.submit()
    assert dlg.result() == 1


def test_no_auto_lock(window):
    assert not hasattr(window, "idle_timer")
    window.forget_verification()
    assert window.vault.unlocked
