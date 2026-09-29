from pathlib import Path

INSTALLER = Path("Install-Fieldora-Complete-Windows.ps1")
CERTIFIED_FIELDORA = "86416455b651d2c087554593093e35cbebf4e268"


def test_complete_installer_pins_certified_whiteboards_runtime():
    text = INSTALLER.read_text(encoding="utf-8")
    assert f'[string]$FieldoraRef = "{CERTIFIED_FIELDORA}"' in text
    assert "63b20df592ca20c6993ede2fc453484f608f49d9" not in text
