# Vault Notes

A fast, encrypted notes and password app for Windows. Press **Ctrl+Alt+N** from anywhere to open it, find a password in seconds, and hide it again.

Everything is stored in **one encrypted file on your PC**. Nothing is sent to the internet.

## Features

- **Global hotkey**: `Ctrl+Alt+N` shows or hides the app from any window; it lives in the system tray.
- **Notes and logins**: plain notes, plus login entries with username, password, URL/server and extra notes.
- **Instant search** across titles, notes, usernames and URLs.
- **One-click copy**: copied passwords are cleared from the clipboard after 30 seconds.
- **Password generator** for strong 20-character passwords.
- **Auto-lock** after 5 minutes idle and whenever Windows is locked.
- **Auto-save** while you type, with a `.bak` copy of the previous save.
- **Backups** to any folder or USB drive (still encrypted).
- **Start with Windows** option.

## Download

Get `VaultNotes.exe` from the [Releases](../../releases) page and double-click it. There is no installer.

Windows SmartScreen may warn about an unknown publisher because the exe is not code-signed. Click **More info → Run anyway**.

## Keyboard shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+Alt+N` | Show / hide (works from anywhere) |
| `Ctrl+N` | New note |
| `Ctrl+L` | New login |
| `Ctrl+F` | Search |
| `Esc` | Hide to tray |
| `Ctrl+Shift+L` | Lock now |

## Security

- The key is derived from your master password with **scrypt** (N=2¹⁷, r=8, p=1, random 16-byte salt).
- Data is encrypted with **AES-256-GCM**, which also detects a wrong password or a tampered file.
- The vault is stored at `%LOCALAPPDATA%\VaultNotes\vault.vnx`.
- **There is no password recovery.** If you forget the master password, the data cannot be decrypted.

This is a personal project and has not had a professional security audit.

## Development

Requires Python 3.11+ on Windows.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -e .

# Run the app
.\.venv\Scripts\python.exe -m vault_notes

# Run the tests
.\.venv\Scripts\python.exe -m pytest

# Build dist\VaultNotes.exe
.\scripts\build.ps1
```

### Project layout

```
vault-notes/
├── .github/workflows/release.yml   # builds the exe and publishes a release on tag push
├── assets/icon.ico                 # app icon (regenerate with scripts/make_icon.py)
├── scripts/
│   ├── build.ps1                   # builds dist/VaultNotes.exe with PyInstaller
│   └── make_icon.py
├── src/vault_notes/
│   ├── __main__.py                 # entry point (python -m vault_notes)
│   ├── app.py                      # window, tray, editor, lock screen
│   ├── crypto.py                   # scrypt + AES-256-GCM file format
│   ├── storage.py                  # load/save/backup of the vault file
│   └── winsys.py                   # hotkey, Windows-lock detection, autostart
├── tests/test_vault.py
├── pyproject.toml
└── requirements.txt
```

### Making a release

Update the version in `pyproject.toml` and `src/vault_notes/__init__.py`, then push a tag:

```powershell
git tag v1.0.0
git push origin v1.0.0
```

GitHub Actions runs the tests, builds `VaultNotes.exe` and attaches it to a new release.

## License

[MIT](LICENSE)
