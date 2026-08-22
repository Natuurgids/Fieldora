from pathlib import Path
from natureai_next.application.project_management import ProjectManagementService


def service(tmp_path: Path):
    s=ProjectManagementService(tmp_path/'science.db')
    p=s.create_project('P',description='',owner_id='admin',actor_id='admin')
    s.set_member_role(p,'alice','contributor',actor_id='admin')
    return s,p


def test_datetime_absence_and_schedule_capacity(tmp_path):
    s,p=service(tmp_path)
    templates=s.schedule_templates()
    forty=next(t for t in templates if t['template_id']=='40-hours')
    s.assign_work_schedule('alice',forty['template_id'],'2026-08-03',reference_week='2026-08-03',actor_id='admin')
    s.add_absence('alice','2026-08-04T10:00:00+00:00','2026-08-04T12:00:00+00:00','medical',actor_id='admin')
    summary=s.capacity_summary('alice','2026-08-03T00:00:00+00:00','2026-08-10T00:00:00+00:00')
    assert summary['scheduled_hours']==40
    assert summary['absence_hours']==2
    assert summary['net_capacity_hours']==38


def test_alternating_schedule_templates(tmp_path):
    s,p=service(tmp_path)
    template=next(t for t in s.schedule_templates() if t['template_id']=='40-32-alternating')
    s.assign_work_schedule('alice',template['template_id'],'2026-08-03',reference_week='2026-08-03',actor_id='admin')
    odd=s.capacity_summary('alice','2026-08-03T00:00:00+00:00','2026-08-10T00:00:00+00:00')
    even=s.capacity_summary('alice','2026-08-10T00:00:00+00:00','2026-08-17T00:00:00+00:00')
    assert odd['scheduled_hours']==40
    assert even['scheduled_hours']==32


def test_obligations_and_project_allocations(tmp_path):
    s,p=service(tmp_path)
    template=next(t for t in s.schedule_templates() if t['template_id']=='40-hours')
    s.assign_work_schedule('alice',template['template_id'],'2026-08-03',actor_id='admin')
    s.add_organisational_obligation('alice','2026-08-05T08:00:00+00:00','2026-08-05T11:00:00+00:00','meeting','Seminar',actor_id='admin')
    s.set_project_allocation('alice',p,'2026-08-03',hours_per_week=10,actor_id='admin')
    summary=s.capacity_summary('alice','2026-08-03T00:00:00+00:00','2026-08-10T00:00:00+00:00',project_id=p)
    assert summary['organisational_hours']==3
    assert summary['allocated_hours']==10
    assert summary['remaining_hours']==27
