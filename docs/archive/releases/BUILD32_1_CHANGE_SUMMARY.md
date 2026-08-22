# Build 32.1 Change Summary

Build 32.1 repairs the Build 32 desktop startup regression. `ModelManagerWorkspace` defines `_ModelInstallProgress(QFrame)` and now imports `QFrame` from `PySide6.QtWidgets` before the class is evaluated. A startup regression test prevents recurrence. No database, library, model, or workflow behavior changed.
