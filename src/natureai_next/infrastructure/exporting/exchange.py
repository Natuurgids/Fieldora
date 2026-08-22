"""Scientific and geospatial exchange writers."""
from __future__ import annotations
import csv, hashlib, io, json, zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring
from natureai_next.domain.exporting import ExportAssetRecord
from natureai_next.infrastructure.filesystem.atomic import atomic_write_bytes

class ExchangeFormatWriter:
    def write_darwin_core(self, destination: Path, records: tuple[ExportAssetRecord, ...], language: str = "en") -> tuple[int,str]:
        occurrence=io.StringIO(newline=""); media=io.StringIO(newline="")
        occ_fields=["id","basisOfRecord","occurrenceID","scientificName","individualCount","sex","lifeStage","behavior","eventDate","identificationVerificationStatus","associatedMedia","language"]
        med_fields=["id","type","identifier","format","references"]
        ow=csv.DictWriter(occurrence,fieldnames=occ_fields,lineterminator="\n"); ow.writeheader()
        mw=csv.DictWriter(media,fieldnames=med_fields,lineterminator="\n"); mw.writeheader()
        media_id=0
        for asset in records:
            media_ref=""
            if asset.primary_path:
                media_id+=1; media_ref=f"media-{media_id}"
                mw.writerow({"id":media_ref,"type":"StillImage" if (asset.mime_type or '').startswith('image/') else "Sound" if (asset.mime_type or '').startswith('audio/') else "MovingImage" if (asset.mime_type or '').startswith('video/') else "PhysicalObject","identifier":asset.primary_path,"format":asset.mime_type or "","references":asset.public_id})
            for obs in asset.observations:
                ow.writerow({"id":obs.get("public_id") or f"{asset.public_id}-observation","basisOfRecord":"HumanObservation","occurrenceID":obs.get("public_id") or "","scientificName":obs.get("scientific_name") or obs.get("user_taxon") or "","individualCount":obs.get("count") or "","sex":obs.get("sex") or "","lifeStage":obs.get("life_stage") or "","behavior":obs.get("behavior") or "","eventDate":_iso_date(asset),"identificationVerificationStatus":obs.get("confirmation_state") or "","associatedMedia":media_ref,"language":language})
        meta=b'''<?xml version="1.0" encoding="UTF-8"?>\n<archive xmlns="http://rs.tdwg.org/dwc/text/" metadata="eml.xml"><core encoding="UTF-8" linesTerminatedBy="\\n" fieldsTerminatedBy="," fieldsEnclosedBy="&quot;" ignoreHeaderLines="1" rowType="http://rs.tdwg.org/dwc/terms/Occurrence"><files><location>occurrence.csv</location></files><id index="0"/></core></archive>\n'''
        eml=(f'<?xml version="1.0" encoding="UTF-8"?>\n<eml><dataset><title>Aperture Darwin Core export</title><language>{language}</language></dataset></eml>\n').encode()
        import tempfile
        destination.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.NamedTemporaryFile(delete=False,dir=destination.parent,suffix='.tmp') as tmp: temp=Path(tmp.name)
        try:
            with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED) as z:
                z.writestr('occurrence.csv',occurrence.getvalue().encode('utf-8-sig')); z.writestr('multimedia.csv',media.getvalue().encode('utf-8-sig')); z.writestr('meta.xml',meta); z.writestr('eml.xml',eml)
            content=temp.read_bytes(); atomic_write_bytes(destination,content)
        finally:
            temp.unlink(missing_ok=True)
        return len(content),hashlib.sha256(content).hexdigest()

    def write_geojson(self,destination:Path,features:tuple[dict[str,object],...])->tuple[int,str]:
        content=(json.dumps({"type":"FeatureCollection","features":features},ensure_ascii=False,sort_keys=True)+"\n").encode(); atomic_write_bytes(destination,content); return len(content),hashlib.sha256(content).hexdigest()

    def write_gpx(self,destination:Path,points:tuple[dict[str,object],...])->tuple[int,str]:
        root=Element('gpx',{'version':'1.1','creator':'Aperture','xmlns':'http://www.topografix.com/GPX/1/1'})
        for point in points:
            w=SubElement(root,'wpt',{'lat':str(point['latitude']),'lon':str(point['longitude'])}); SubElement(w,'name').text=str(point.get('name','Observation')); SubElement(w,'desc').text=str(point.get('description',''))
        content=b'<?xml version="1.0" encoding="UTF-8"?>\n'+tostring(root,encoding='utf-8')+b'\n'; atomic_write_bytes(destination,content); return len(content),hashlib.sha256(content).hexdigest()

def _iso_date(asset:ExportAssetRecord)->str:
    if asset.capture_time_utc_us:
        return datetime.fromtimestamp(asset.capture_time_utc_us/1_000_000,tz=timezone.utc).isoformat()
    return asset.capture_local_text or ""
