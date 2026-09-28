from pathlib import Path

INSTALLER = Path("Install-Fieldora-Complete-Windows.ps1")
CERTIFIED_FIELDORA = "7c49b936cb06273e98526c2f7060a064b502804f"


def test_complete_installer_pins_certified_whiteboards_runtime():
    text = INSTALLER.read_text(encoding="utf-8")
    assert f'[string]$FieldoraRef = "{CERTIFIED_FIELDORA}"' in text
    assert "63b20df592ca20c6993ede2fc453484f608f49d9" not in text
