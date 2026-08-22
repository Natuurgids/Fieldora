from __future__ import annotations
from pathlib import Path
from PySide6.QtWidgets import QDialog,QDialogButtonBox,QFormLayout,QLabel,QLineEdit,QMessageBox,QVBoxLayout
from natureai_next.application.local_profiles import LocalProfileStore
class LocalLoginDialog(QDialog):
 def __init__(self,path:Path,parent=None):
  super().__init__(parent);self.store=LocalProfileStore(path);self.profile=None;self.setWindowTitle('Fieldora sign in');self.setMinimumWidth(420)
  box=QVBoxLayout(self);box.addWidget(QLabel('<h2>Fieldora</h2><p>Local evaluation sign-in</p>'))
  form=QFormLayout();self.username=QLineEdit('admin');self.password=QLineEdit('admin');self.password.setEchoMode(QLineEdit.EchoMode.Password);form.addRow('Username',self.username);form.addRow('Password',self.password);box.addLayout(form)
  hint=QLabel('Evaluation profiles: admin, project_manager, researcher, reviewer, viewer. Initial password: admin.');hint.setWordWrap(True);box.addWidget(hint)
  buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(self._login);buttons.rejected.connect(self.reject);box.addWidget(buttons)
 def _login(self):
  try:self.profile=self.store.authenticate(self.username.text(),self.password.text())
  except Exception as exc:QMessageBox.warning(self,'Sign in',str(exc));return
  self.accept()
