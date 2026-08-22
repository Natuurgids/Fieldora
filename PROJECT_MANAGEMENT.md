# Project & Work Management

Fieldora 0.11 replaces the former lightweight Science project planner with a
dedicated work-management domain. Existing legacy project snapshot rows are not
migrated or displayed.

Each project provides synchronized task list, Kanban, grid, Gantt, calendar,
workload, dashboard, activity, and administration screens. Tasks support
owners, strict dates, priorities, milestones, subtasks, checklists,
finish-to-start dependencies, recurrence, sprint labels, estimates, budgets,
progress, custom fields, and configurable workflow states with WIP limits.

Collaboration includes threaded task comments, `@identity` notifications,
external links, local attachments and attachment versions. Planning includes
time logging, weekly capacity, cost rates, leave/PTO, templates, milestones,
and workload forecasting.

Project roles are Admin, Manager, Contributor, and Guest. Client portal previews
expose only project health and milestones and exclude internal comments, files,
activity, time, and capacity data. Dashboards include completion, overdue and
blocked work, estimate-versus-actual totals, cumulative flow, and sprint
metrics. Reports export to CSV, Excel, and PDF.

The normalized `pm_*` tables reside in `science.sqlite3` and use foreign keys,
WAL mode, transactions, and an explicit schema marker.
