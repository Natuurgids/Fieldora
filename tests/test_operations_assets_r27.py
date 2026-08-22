from pathlib import Path
from natureai_next.application.operations_assets import OperationsAssetService
from natureai_next.ui.qt.navigation_contracts import workspace_names


def test_operations_schema_and_exact_storage_path(tmp_path: Path):
    svc=OperationsAssetService(tmp_path/'science.sqlite3')
    site=svc.add_location('site','LOUVRE','Louvre')
    hall=svc.add_location('hall','H3','Hall 3',site)
    floor=svc.add_location('floor','F3','3rd floor',hall)
    wing=svc.add_location('wing','LEFT','Left wing',floor)
    room=svc.add_location('room','R8','Room 8',wing)
    cabinet=svc.add_location('cabinet','CS8-7','Cabinet CS8-7',room)
    drawer=svc.add_location('drawer','D8','Drawer 8',cabinet)
    part=svc.add_location('part','C3','Part C3',drawer)
    path=svc.location_path(part)
    assert 'Louvre' in path and 'CS8-7' in path and 'C3' in path
    asset=svc.add_asset('EQ-001','Precision scale','measuring equipment','admin',location_id=part)
    assert svc.assets()[0]['id']==asset


def test_operations_documents_drawings_and_service_records(tmp_path: Path):
    svc=OperationsAssetService(tmp_path/'science.sqlite3')
    room=svc.add_location('room','R1','Room 1')
    asset=svc.add_asset('CAM-1','Camera','field equipment','admin',location_id=room,image_path='/tmp/camera.jpg')
    svc.add_document(asset,'manual','Manual','/tmp/manual.pdf','admin','application/pdf')
    drawing=svc.add_drawing('Floor plan','svg','/tmp/floor.svg','admin',location_id=room,version='1')
    svc.add_storage_condition(room,'Cool dry',15,20,30,50,monitoring_required=True)
    svc.add_drawing_marker(drawing,'R1',12.5,18.0,location_id=room)
    svc.add_maintenance(asset,'preventive','planned','admin')
    svc.add_calibration(asset,'planned','admin',standard_reference='ISO 17025')
    assert len(svc.drawings())==1
    assert len(svc.drawing_markers())==1
    assert len(svc.maintenance())==1
    assert len(svc.calibrations())==1


def test_operations_workspace_is_registered():
    assert 'Asset & Equipment Operations' in workspace_names()
