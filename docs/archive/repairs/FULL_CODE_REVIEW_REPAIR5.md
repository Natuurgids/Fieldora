# Aperture Build 26 Repair 5

Repair 5 closes the remaining startup gap between library-open validation and eager Qt workspace queries.

The library is now revalidated after desktop service composition and immediately before `MainWindow` construction. If an empty clean-start database has lost or changed its schema during startup, it is rebuilt, fully validated, and the external NatureAI bridge is registered again. Libraries containing user data are never destructively rebuilt.

Regression coverage includes schema drift introduced after a library has already been opened.
