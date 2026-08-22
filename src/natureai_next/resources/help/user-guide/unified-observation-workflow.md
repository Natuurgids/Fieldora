# Unified observation workflow

Fieldora 5.2 treats an observation as the scientific record for an occurrence at a
place and time. Photos, sounds, videos, documents and measurements are evidence for
that observation; they are not separate identifications.

## Identification history

The observer, local AI, external references, specialists and authorities can each add
an identification assertion. Assertions are append-only and retain author, confidence,
evidence, rationale and time. Accepting an assertion supersedes a previous accepted
assertion without deleting it. A disputed assertion returns the observation to review.

## Specialist referral

Use **Refer to specialist** from Observations. Select an authority level from 1 to 9
and record the question. A specialist can respond, or escalate the same referral to a
higher authority. Every referral remains in the observation history.

## Research relationships

An observation can be linked independently to projects, dossiers and collections.
A project defines research work and an area; a dossier curates a project or a
longitudinal subject; a collection is a flexible working selection.

## Structured project export

From Research, select a project and choose **Export project package**. Select tasks,
notes, GeoJSON areas, map snapshots, evidence index and optional original media. The
archive contains JSON, CSV, HTML and a SHA-256 inventory in its manifest.

## Observation.org

Reporting → Connectors includes explicit authenticated exchange. The test environment
is the default. Paste an OAuth2 access token for the current session, inspect the JSON
payload, and explicitly select production before sending. Fieldora does not store the
token in the library. Successful remote identifiers are recorded with the observation.
