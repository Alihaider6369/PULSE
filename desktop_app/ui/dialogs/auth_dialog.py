"""Authentication dialog for desktop app: Login and Registration."""
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from desktop_app.core.client import PulseApiClient
from desktop_app.ui.theme import COLORS


class AuthDialog(QDialog):
    """Modal dialog allowing users to sign in or create an account."""

    def __init__(self, api_client: PulseApiClient, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.api_client = api_client
        self.is_signup_mode = False

        self.setWindowTitle("PULSE — Account Authentication")
        self.setFixedWidth(420)
        self.setStyleSheet(f"""
            QDialog {{ background-color: {COLORS['bg_dark']}; }}
            QLabel {{ color: {COLORS['text_main']}; font-family: 'Segoe UI', sans-serif; }}
            QLineEdit {{
                background-color: {COLORS['surface_light']};
                border: 1px solid {COLORS['border_light']};
                border-radius: 6px;
                color: {COLORS['text_main']};
                padding: 8px 12px;
                font-size: 13px;
            }}
            QLineEdit:focus {{ border: 1px solid {COLORS['primary']}; }}
        """)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        # Title
        self.lbl_title = QLabel("Sign in to PULSE")
        self.lbl_title.setStyleSheet("font-size: 20px; font-weight: bold; color: #f8fafc;")
        layout.addWidget(self.lbl_title)

        self.lbl_subtitle = QLabel("Synchronize your ergonomic sessions across devices")
        self.lbl_subtitle.setStyleSheet(f"font-size: 12px; color: {COLORS['text_muted']};")
        layout.addWidget(self.lbl_subtitle)

        # Full Name (visible only on signup)
        self.lbl_name = QLabel("Full Name:")
        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText("Jane Doe")
        self.lbl_name.setVisible(False)
        self.txt_name.setVisible(False)
        layout.addWidget(self.lbl_name)
        layout.addWidget(self.txt_name)

        # Email
        lbl_email = QLabel("Email Address:")
        self.txt_email = QLineEdit()
        self.txt_email.setPlaceholderText("name@example.com")
        layout.addWidget(lbl_email)
        layout.addWidget(self.txt_email)

        # Password
        lbl_password = QLabel("Password:")
        self.txt_password = QLineEdit()
        self.txt_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_password.setPlaceholderText("At least 8 characters")
        layout.addWidget(lbl_password)
        layout.addWidget(self.txt_password)

        # Status / Error Label
        self.lbl_msg = QLabel("")
        self.lbl_msg.setWordWrap(True)
        self.lbl_msg.setStyleSheet(f"font-size: 12px; color: {COLORS['danger']};")
        layout.addWidget(self.lbl_msg)

        # Submit Button
        self.btn_submit = QPushButton("Sign In")
        self.btn_submit.setProperty("class", "primary_button")
        self.btn_submit.setMinimumHeight(40)
        self.btn_submit.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['primary']};
                color: #ffffff;
                font-weight: 600;
                border-radius: 8px;
                border: none;
            }}
            QPushButton:hover {{ background-color: {COLORS['primary_hover']}; }}
        """)
        self.btn_submit.clicked.connect(self._handle_submit)
        layout.addWidget(self.btn_submit)

        # Toggle mode button
        toggle_row = QHBoxLayout()
        self.lbl_toggle = QLabel("Don't have an account?")
        self.lbl_toggle.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 12px;")
        self.btn_toggle = QPushButton("Create one")
        self.btn_toggle.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: {COLORS['primary']};
                font-weight: 600;
                font-size: 12px;
                text-decoration: underline;
            }}
            QPushButton:hover {{ color: {COLORS['primary_hover']}; }}
        """)
        self.btn_toggle.clicked.connect(self._toggle_mode)
        toggle_row.addWidget(self.lbl_toggle)
        toggle_row.addWidget(self.btn_toggle)
        toggle_row.addStretch()
        layout.addLayout(toggle_row)

    def _toggle_mode(self) -> None:
        self.is_signup_mode = not self.is_signup_mode
        self.lbl_msg.setText("")
        if self.is_signup_mode:
            self.lbl_title.setText("Create PULSE Account")
            self.btn_submit.setText("Register & Sign In")
            self.lbl_toggle.setText("Already registered?")
            self.btn_toggle.setText("Sign in")
            self.lbl_name.setVisible(True)
            self.txt_name.setVisible(True)
        else:
            self.lbl_title.setText("Sign in to PULSE")
            self.btn_submit.setText("Sign In")
            self.lbl_toggle.setText("Don't have an account?")
            self.btn_toggle.setText("Create one")
            self.lbl_name.setVisible(False)
            self.txt_name.setVisible(False)

    def _handle_submit(self) -> None:
        email = self.txt_email.text().strip()
        password = self.txt_password.text().strip()
        self.lbl_msg.setText("")

        if not email or "@" not in email:
            self.lbl_msg.setText("Please enter a valid email address.")
            return

        if len(password) < 8:
            self.lbl_msg.setText("Password must be at least 8 characters long.")
            return

        if self.is_signup_mode:
            name = self.txt_name.text().strip() or None
            ok, msg = self.api_client.signup(email=email, password=password, full_name=name)
        else:
            ok, msg = self.api_client.login(email=email, password=password)

        if ok:
            self.accept()
        else:
            self.lbl_msg.setText(msg)
