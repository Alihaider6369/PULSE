"""Stylesheets and visual themes for PULSE Desktop."""

COLORS = {
    "bg_dark": "#0b0f19",
    "surface": "#131b2e",
    "surface_light": "#1e293b",
    "surface_hover": "#26334d",
    "border": "#283548",
    "border_light": "#3b4a63",
    "text_main": "#f8fafc",
    "text_muted": "#94a3b8",
    "primary": "#6366f1",
    "primary_hover": "#4f46e5",
    "primary_pressed": "#4338ca",
    "success": "#10b981",
    "success_bg": "rgba(16, 185, 129, 0.15)",
    "warning": "#f59e0b",
    "warning_bg": "rgba(245, 158, 11, 0.15)",
    "danger": "#ef4444",
    "danger_bg": "rgba(239, 68, 68, 0.15)",
    "cyan": "#06b6d4",
}

STYLESHEET = f"""
QMainWindow {{
    background-color: {COLORS['bg_dark']};
}}

QWidget {{
    color: {COLORS['text_main']};
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
    font-size: 13px;
}}

/* Sidebar navigation */
QFrame#sidebar {{
    background-color: {COLORS['surface']};
    border-right: 1px solid {COLORS['border']};
}}

QLabel#brand_title {{
    font-size: 20px;
    font-weight: bold;
    color: {COLORS['text_main']};
    padding: 12px 16px 2px 16px;
    letter-spacing: 1px;
}}

QLabel#brand_subtitle {{
    font-size: 11px;
    color: {COLORS['text_muted']};
    padding: 0px 16px 16px 16px;
}}

QPushButton.nav_button {{
    background-color: transparent;
    color: {COLORS['text_muted']};
    border: none;
    text-align: left;
    padding: 12px 20px;
    font-size: 13px;
    font-weight: 500;
    border-radius: 8px;
    margin: 3px 10px;
}}

QPushButton.nav_button:hover {{
    background-color: {COLORS['surface_hover']};
    color: {COLORS['text_main']};
}}

QPushButton.nav_button:checked {{
    background-color: {COLORS['primary']};
    color: #ffffff;
    font-weight: 600;
}}

/* Card container */
QFrame.card {{
    background-color: {COLORS['surface']};
    border: 1px solid {COLORS['border']};
    border-radius: 12px;
}}

QFrame.card_inner {{
    background-color: {COLORS['surface_light']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
}}

/* Buttons */
QPushButton.primary_button {{
    background-color: {COLORS['primary']};
    color: #ffffff;
    font-weight: 600;
    padding: 10px 20px;
    border-radius: 8px;
    border: none;
}}

QPushButton.primary_button:hover {{
    background-color: {COLORS['primary_hover']};
}}

QPushButton.primary_button:pressed {{
    background-color: {COLORS['primary_pressed']};
}}

QPushButton.secondary_button {{
    background-color: {COLORS['surface_light']};
    color: {COLORS['text_main']};
    border: 1px solid {COLORS['border_light']};
    padding: 9px 18px;
    border-radius: 8px;
    font-weight: 500;
}}

QPushButton.secondary_button:hover {{
    background-color: {COLORS['surface_hover']};
}}

QPushButton.danger_button {{
    background-color: {COLORS['danger']};
    color: #ffffff;
    font-weight: 600;
    padding: 10px 20px;
    border-radius: 8px;
    border: none;
}}

QPushButton.danger_button:hover {{
    background-color: #dc2626;
}}

/* Table Widget */
QTableWidget {{
    background-color: {COLORS['surface']};
    border: 1px solid {COLORS['border']};
    gridline-color: {COLORS['border']};
    border-radius: 8px;
    color: {COLORS['text_main']};
    selection-background-color: {COLORS['surface_hover']};
    selection-color: #ffffff;
}}

QHeaderView::section {{
    background-color: {COLORS['surface_light']};
    color: {COLORS['text_muted']};
    font-weight: 600;
    padding: 8px 12px;
    border: none;
    border-bottom: 1px solid {COLORS['border']};
}}

/* Input widgets */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background-color: {COLORS['surface_light']};
    border: 1px solid {COLORS['border_light']};
    border-radius: 6px;
    color: {COLORS['text_main']};
    padding: 7px 10px;
}}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border: 1px solid {COLORS['primary']};
}}

QComboBox QAbstractItemView {{
    background-color: {COLORS['surface_light']};
    border: 1px solid {COLORS['border']};
    selection-background-color: {COLORS['primary']};
}}

QCheckBox {{
    color: {COLORS['text_main']};
    spacing: 8px;
}}

QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 1px solid {COLORS['border_light']};
    background-color: {COLORS['surface_light']};
}}

QCheckBox::indicator:checked {{
    background-color: {COLORS['primary']};
    border-color: {COLORS['primary']};
}}

/* Scroll bars */
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 0px;
}}

QScrollBar::handle:vertical {{
    background: {COLORS['border_light']};
    border-radius: 4px;
    min-height: 20px;
}}

QScrollBar::handle:vertical:hover {{
    background: {COLORS['text_muted']};
}}
"""
