from pathlib import Path
from natureai_next.application.project_management import ProjectManagementService


def test_specimen_enrichment_longitudinal_audit_and_cross_project(tmp_path: Path):
    service=ProjectManagementService(tmp_path/'science.sqlite')
    p1=service.create_project(name='Bird study',owner_id='alice',actor_id='alice')
    p2=service.create_project(name='Other',owner_id='bob',actor_id='bob')
    specimen=service.create_specimen(p1,specimen_code='BIRD-1',taxon_name='Turdus merula',actor_id='alice')
    service.add_specimen_identifier(specimen,identifier_type='ring',identifier_value='NL-1',actor_id='alice')
    e1=service.record_specimen_enrichment(p1,specimen,enrichment_type='measurement',occurred_at='2026-01-01T10:00',value_text='92',unit='g',actor_id='alice')
    e2=service.record_specimen_enrichment(p1,specimen,enrichment_type='measurement',occurred_at='2028-01-01T10:00',value_text='99',unit='g',actor_id='alice')
    assert [x['enrichment_id'] for x in service.specimen_enrichments(p1)] == [e2,e1]
    assert service.specimen_identifiers(p1)[0]['recorded_by']=='alice'
    try:
        service.record_specimen_enrichment(p2,specimen,enrichment_type='observation',occurred_at='2028-01-01',actor_id='bob')
    except ValueError:
        pass
    else:
        raise AssertionError('cross-project specimen enrichment accepted')
    events=[x['event_type'] for x in service.activity(p1)]
    assert 'specimen.created' in events and 'specimen.identifier_added' in events and 'enrichment.recorded' in events


def test_managed_statuses_samples_survey_lab_and_media(tmp_path: Path):
    service=ProjectManagementService(tmp_path/'science.sqlite')
    project=service.create_project(name='Study',owner_id='alice',actor_id='alice')
    assert any(x['code']=='completed' for x in service.reference_values('laboratory_status'))
    service.save_reference_value('party','university_lab','University laboratory',actor_id='local-user')
    assert any(x['code']=='university_lab' for x in service.reference_values('party'))
    event=service.create_survey_event(project,name='Capture 1',actor_id='alice')
    service.update_survey_event_status(event,'completed',actor_id='alice')
    sample=service.create_sample(project,sample_code='S-1',sample_type='blood',actor_id='alice')
    service.update_sample_status(sample,'received',actor_id='alice')
    lab=service.add_laboratory_record(sample,record_type='radiology',laboratory='University laboratory',status='requested',actor_id='alice')
    service.update_laboratory_status(lab,'completed',actor_id='alice')
    image=tmp_path/'xray.png'; image.write_bytes(b'not-a-real-image-but-an-immutable-test-asset')
    media=service.add_laboratory_media(lab,image,media_type='image',modality='x_ray',actor_id='alice')
    row=service.laboratory_media(project)[0]
    assert row['media_id']==media and row['media_type']=='image' and row['modality']=='x_ray' and row['uploaded_by']=='alice'
    assert service.samples(project)[0]['status']=='received'
    assert service.survey_events(project)[0]['status']=='completed'
    assert service.sample_workflow_records(project)['laboratory_records'][0]['status']=='completed'
