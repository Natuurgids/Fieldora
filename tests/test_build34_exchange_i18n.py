from __future__ import annotations
import csv, json, zipfile
from pathlib import Path
from natureai_next.application.connectors import ConnectorRegistry
from natureai_next.application.localization import LocaleService, TranslationCatalog, normalize_locale
from natureai_next.domain.exporting import ExportAssetRecord
from natureai_next.infrastructure.exporting.exchange import ExchangeFormatWriter

def record(*, observation=True):
    observations = ({"public_id":"obs-1","scientific_name":"Corvus corax","count":2,"confirmation_state":"accepted"},) if observation else ()
    return ExportAssetRecord("asset-1",1,"Raven",None,None,5,None,None,1_700_000_000_000_000,None,"/tmp/raven.jpg","abc","image/jpeg","JPEG",100,100,("bird",),observations)

def test_locale_fallback_and_normalization(tmp_path: Path):
    root=tmp_path/'i18n'; root.mkdir(); (root/'en.json').write_text(json.dumps({'hello':'Hello {name}'})); (root/'nl.json').write_text(json.dumps({'hello':'Hallo {name}'}))
    service=LocaleService(TranslationCatalog(root),'nl-NL')
    assert service.translate('hello',name='Ada') == 'Hallo Ada'
    assert service.translate('missing','Fallback') == 'Fallback'
    assert normalize_locale('xx-YY') == 'en'

def test_darwin_core_archive(tmp_path: Path):
    destination=tmp_path/'export.zip'
    size,digest=ExchangeFormatWriter().write_darwin_core(destination,(record(),),'nl')
    assert size == destination.stat().st_size and len(digest)==64
    with zipfile.ZipFile(destination) as archive:
        assert {'occurrence.csv','multimedia.csv','meta.xml','eml.xml'} <= set(archive.namelist())
        rows=list(csv.DictReader(archive.read('occurrence.csv').decode('utf-8-sig').splitlines()))
        assert rows[0]['scientificName']=='Corvus corax'
        assert rows[0]['language']=='nl'

def test_connector_registry_preflight_is_offline_and_explicit():
    registry=ConnectorRegistry()
    assert {'waarneming-nl','observation-org','inaturalist','gbif'} <= {item.connector_id for item in registry.list()}
    result=registry.validate('waarneming-nl',(record(),))
    assert result.valid_count == 0
    assert result.invalid_count == 1
    assert 'location' in result.warnings[0]
