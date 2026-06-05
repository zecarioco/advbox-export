from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from advbox_export.core.config import Config, ConfigStore


class SettingsDialog(QDialog):
    def __init__(self, store: ConfigStore, parent=None) -> None:
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("Configurações — AdvBox Export")
        self.setMinimumWidth(520)

        cfg = store.load()

        layout = QVBoxLayout(self)

        intro = QLabel(
            "Cole o token AdvBox abaixo. Ele será gravado no arquivo de "
            "configuração local e usado em todas as próximas execuções."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.token_input = QLineEdit(cfg.token)
        self.token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.token_input.setPlaceholderText("Bearer token fornecido pela AdvBox")
        form.addRow("Token:", self.token_input)

        self.mostrar_token = QCheckBox("Mostrar token")
        self.mostrar_token.toggled.connect(self._toggle_echo)
        form.addRow("", self.mostrar_token)

        self.base_url_input = QLineEdit(cfg.base_url)
        form.addRow("Base URL:", self.base_url_input)

        layout.addLayout(form)

        caminho = QLabel(f"Arquivo: {store.path}")
        caminho.setStyleSheet("color: gray; font-size: 11px;")
        caminho.setWordWrap(True)
        layout.addWidget(caminho)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._salvar)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _toggle_echo(self, checked: bool) -> None:
        self.token_input.setEchoMode(
            QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        )

    def _salvar(self) -> None:
        token = self.token_input.text().strip()
        base_url = self.base_url_input.text().strip()

        if not token:
            QMessageBox.warning(self, "Token obrigatório", "Cole o token AdvBox antes de salvar.")
            return
        if not base_url:
            QMessageBox.warning(self, "Base URL obrigatória", "Informe a base URL da API.")
            return

        self.store.save(Config(token=token, base_url=base_url))
        self.accept()
