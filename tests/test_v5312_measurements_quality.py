import csv
import json
import zipfile

from natureai_next.application.project_management import ProjectExportOptions, ProjectManagementService, QUALITY_RULES


def test_measurements_samples_lab_custody_csv_and_quality(tmp_path):
    service=ProjectManagementService(tmp_path/'projects.sqlite3'); project=service.create_project('Water survey',owner_id='lead',actor_id='lead')
    definition=service.create_measurement_definition(project,name='pH',category='water',unit='pH',minimum=0,maximum=14,actor_id='lead')
    sample=service.create_sample(project,sample_code='W-001',sample_type='water',container='glass bottle',preservation='chilled',actor_id='lead')
    service.record_measurement(project,name='pH',value='20',unit='pH',category='water',definition_id=definition,sample_id=sample,instrument='meter',calibration_reference='CAL-1',uncertainty=.1,actor_id='lead')
    service.add_custody_event(sample,action='transfer',to_party='Lab A',occurred_at='2026-08-02 10:00',actor_id='lead')
    service.add_laboratory_record(sample,record_type='request',laboratory='Lab A',requested_test='nutrients',actor_id='lead')
    source=tmp_path/'instrument.csv'
    with source.open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=('name','value','unit','instrument','uncertainty'));writer.writeheader();writer.writerow({'name':'salinity','value':'3.2','unit':'ppt','instrument':'probe','uncertainty':'0.05'})
    assert service.import_instrument_csv(project,source,actor_id='lead') == 1
    assert service.run_quality_checks(project,actor_id='lead') == 3
    findings=service.quality_findings(project); anomalous=next(row for row in findings if row['rule_code']=='anomalous_measurement')
    assert 'Review the recorded measurement' in anomalous['explanation']
    service.dismiss_quality_finding(anomalous['finding_id'],reason='Meter was deliberately tested with reference fluid',actor_id='lead')
    assert next(row for row in service.quality_findings(project) if row['finding_id']==anomalous['finding_id'])['dismissed_by']=='lead'
    output=service.export_research_package(project,tmp_path/'export.zip',options=ProjectExportOptions())
    with zipfile.ZipFile(output) as package:
        assert {'data/measurements-samples.json','data/quality-findings.json'} <= set(package.namelist())
        assert json.loads(package.read('data/measurements-samples.json'))['samples'][0]['sample_code']=='W-001'


def test_quality_catalog_and_research_routes_are_complete():
    assert set(QUALITY_RULES)=={'missing_coordinates','missing_date','impossible_coordinates','outside_expected_range','duplicate_observation','conflicting_identification','low_quality_evidence','missing_licence_consent','taxonomy_mismatch','anomalous_measurement','incomplete_sampling_protocol'}
    desktop=open('src/natureai_next/ui/qt/v5_desktop.py',encoding='utf-8').read(); app=open('src/natureai_next/ui/qt/application.py',encoding='utf-8').read(); ui=open('src/natureai_next/ui/qt/project_management.py',encoding='utf-8').read()
    for route in ('__project_measurements__','__project_quality__'): assert route in desktop and route in app
    assert 'Measurements & Samples' not in ui
    assert '_measurements_tab_index' not in ui
    assert '_build_operations_link_page' in ui and 'Data Quality' in ui
