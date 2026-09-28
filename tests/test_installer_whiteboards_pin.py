from pathlib import Path

INSTALLER = Path("Install-Fieldora-Complete-Windows.ps1")
CERTIFIED_FIELDORA = "7480e9fc63e64e06e8ebc0159aa76ca16c92393f"


def test_complete_installer_pins_certified_whiteboards_runtime():
    text = INSTALLER.read_text(encoding="utf-8")
    assert f'[string]$FieldoraRef = "{CERTIFIED_FIELDORA}"' in text
    assert "63b20df592ca20c6993ede2fc453484f608f49d9" not in text
