# Marine and maritime workspaces

Fieldora separates environmental evidence from the logistics used to collect it.
Both workspaces are local-first and enabled by default. An administrator can
switch either one off under **Platform > Library Administration > Enabled
Modules** without deleting its records.

## Marine & Freshwater Science

Open **Research > Scientific Records > Marine & Freshwater Science**. The
workspace provides dedicated screens for:

- sampling stations and surveys;
- physical samples and environmental measurements;
- species observations and eDNA samples;
- marine and freshwater habitats; and
- acoustic and sonar evidence.

Create a record on the appropriate tab. Names are required. Status, owner,
start/end time, coordinates and notes are optional. Select media in the Library
before choosing **Attach selected library media** to associate photos, sounds,
videos or documents with the selected record.

## Maritime Operations

Open **Research > Maritime Operations**. Operational records are
kept separate from scientific conclusions. Dedicated screens cover:

- vessels and voyages;
- ports and routes;
- crew and equipment;
- dives and depth-aware submarine logs; and
- chronological operation logs.

Depth is recorded in metres below the surface and is available on every
maritime registration screen so dives, submarine missions and other operational
logs use one consistent field.

The **Dives** registration additionally records **Buddy / dive partner** as a
dedicated field. It is displayed in the Dive Log and included in JSON exports.

The same attachment mechanism can link manifests, safety documents, photographs,
video or acoustic recordings without copying the media.

## Export, audit and access

**Export domain JSON** produces the `fieldora.marine-maritime.v1` portable
contract, including record fields and linked asset identifiers. Creation,
deletion and attachment actions produce immutable audit events in the dedicated
`marine-maritime.sqlite3` subsystem database.

Module visibility is independent: disabling Marine Science does not disable
Maritime Operations, and vice versa. Existing Fieldora access contracts remain
the authority for exporting or transmitting attached Library assets; a record
link does not grant additional access to the underlying media.
