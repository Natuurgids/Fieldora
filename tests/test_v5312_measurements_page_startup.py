from pathlib import Path


def test_page_header_allows_missing_action() -> None:
    source = Path('src/natureai_next/ui/qt/v5_desktop.py').read_text(encoding='utf-8')
    assert "if action is not None:self.header.addWidget(self.button(*action,True))" in source
    assert "self.header.addWidget(self.button(*action,True));self.body.addLayout(self.header)" not in source


def test_measurements_page_intentionally_has_no_header_action() -> None:
    source = Path('src/natureai_next/ui/qt/v5_desktop.py').read_text(encoding='utf-8')
    assert "super().__init__('Specimen Enrichments, Samples & Protocols',None,parent)" in source
