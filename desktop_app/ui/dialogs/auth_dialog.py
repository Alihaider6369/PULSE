import re
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

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AuthDialog(QDialog):
    """Modal dialog allowing users to sign in, create an account, or request password reset."""

    def __init__(self, api_client: PulseApiClient, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.api_client = api_client
        self.mode = "login"  # "login", "signup", "forgot"

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
        self.password_container = QWidget()
        pwd_layout = QVBoxLayout(self.password_container)
        pwd_layout.setContentsMargins(0, 0, 0, 0)
        pwd_layout.setSpacing(6)

        pwd_header = QHBoxLayout()
        lbl_password = QLabel("Password:")
        lbl_password.setStyleSheet("font-size: 13px;")
        self.btn_forgot = QPushButton("Forgot password?")
        self.btn_forgot.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: #818cf8;
                font-size: 11px;
                text-decoration: underline;
            }}
            QPushButton:hover {{ color: {COLORS['primary_hover']}; }}
        """)
        self.btn_forgot.clicked.connect(lambda: self._set_mode("forgot"))
        pwd_header.addWidget(lbl_password)
        pwd_header.addStretch()
        pwd_header.addWidget(self.btn_forgot)
        pwd_layout.addLayout(pwd_header)

        self.txt_password = QLineEdit()
        self.txt_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_password.setPlaceholderText("At least 8 characters")
        pwd_layout.addWidget(self.txt_password)

        layout.addWidget(self.password_container)

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

    def _set_mode(self, mode: str) -> None:
        self.mode = mode
        self.lbl_msg.setText("")
        self.lbl_msg.setStyleSheet(f"font-size: 12px; color: {COLORS['danger']};")

        if mode == "signup":
            self.lbl_title.setText("Create PULSE Account")
            self.lbl_subtitle.setText("Start tracking your posture habits privately")
            self.btn_submit.setText("Register & Sign In")
            self.lbl_toggle.setText("Already registered?")
            self.btn_toggle.setText("Sign in")
            self.lbl_name.setVisible(True)
            self.txt_name.setVisible(True)
            self.password_container.setVisible(True)
            self.btn_forgot.setVisible(False)
        elif mode == "forgot":
            self.lbl_title.setText("Reset Password")
            self.lbl_subtitle.setText("Enter your email to receive a password reset link")
            self.btn_submit.setText("Send Reset Link")
            self.lbl_toggle.setText("Remembered password?")
            self.btn_toggle.setText("Sign in")
            self.lbl_name.setVisible(False)
            self.txt_name.setVisible(False)
            self.password_container.setVisible(False)
        else:
            self.mode = "login"
            self.lbl_title.setText("Sign in to PULSE")
            self.lbl_subtitle.setText("Synchronize your ergonomic sessions across devices")
            self.btn_submit.setText("Sign In")
            self.lbl_toggle.setText("Don't have an account?")
            self.btn_toggle.setText("Create one")
            self.lbl_name.setVisible(False)
            self.txt_name.setVisible(False)
            self.password_container.setVisible(True)
            self.btn_forgot.setVisible(True)

    def _toggle_mode(self) -> None:
        if self.mode == "login":
            self._set_mode("signup")
        else:
            self._set_mode("login")

    def _handle_submit(self) -> None:
        email = self.txt_email.text().strip()
        self.lbl_msg.setText("")
        self.lbl_msg.setStyleSheet(f"font-size: 12px; color: {COLORS['danger']};")

        # 1. Client-side email validation
        if not email or not EMAIL_REGEX.match(email):
            self.lbl_msg.setText("Enter a valid email address")
            return

        if self.mode == "forgot":
            ok, msg = self.api_client.forgot_password(email=email)
            if ok:
                self.lbl_msg.setStyleSheet(f"font-size: 12px; color: {COLORS['success']};")
                self.lbl_msg.setText(msg)
            else:
                self.lbl_msg.setText(msg)
            return

        password = self.txt_password.text().strip()
        if len(password) < 8:
            self.lbl_msg.setText("Password must be at least 8 characters long")
            return

        if self.mode == "signup":
            name = self.txt_name.text().strip() or None
            ok, msg = self.api_client.signup(email=email, password=password, full_name=name)
        else:
            ok, msg = self.api_client.login(email=email, password=password)

        if ok:
            self.accept()
        else:
            self.lbl_msg.setText(msg)
