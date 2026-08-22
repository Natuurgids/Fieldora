# Home and research calendar

## Home

Fieldora opens on **Home**. This is an operational research overview rather than
a second navigation tree. It shows:

- total Library assets;
- open project tasks;
- planned research activities;
- Marine & Freshwater Science records; and
- activities and incomplete task deadlines in the next 30 days.

Use the cards or quick-action buttons to open the corresponding workspace.
Choose **Refresh overview** after a long-running import or processing job if the
counts have not yet changed.

## Calendar activity markers

The Research Calendar and the calendar inside Projects & Tasks highlight every
date with planned work. A gold badge shows the number of activities, task starts
or task deadlines on that day. `99+` is shown when more than 99 items fall on a
single date. Selecting the date shows its individual items.

## Google Calendar and Outlook

The Research Calendar supports three deliberate outbound actions:

- **Export calendar (.ics)** writes all Fieldora research activities and project
  activity deadlines in the standard iCalendar format. The file can be imported
  by Google Calendar, Outlook, Apple Calendar and most CalDAV applications.
- **Add selected to Google Calendar** opens Google's event composer with the
  selected activity prefilled.
- **Add selected to Outlook** opens Outlook's event composer with the selected
  activity prefilled.

Fieldora does not transmit calendar data in the background. The provider action
occurs only after the user selects an event and presses a provider button.

Continuous two-way synchronization is technically possible through Google
Calendar API and Microsoft Graph adapters. It requires an organization-specific
OAuth application, administrator consent, encrypted token storage, access
contracts, audit events, conflict handling and deletion policy. That mode is not
enabled by the portable compose-link and iCalendar integration.
