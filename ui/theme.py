"""Gemeinsame Farben und Gestaltung für alle nativen Qt-Widgets."""

COLORS = {
    "bg": "#101722",
    "surface": "#192332",
    "muted": "#98a8bd",
    "accent": "#62dfb6",
    "text": "#edf3fa",
}

STYLESHEET = """
QWidget { color: #edf3fa; font-family: 'Segoe UI'; font-size: 10pt; }
QMainWindow, QDialog { background: #101722; }
QLabel { background: transparent; }
QFrame#sidebar { background: #121c29; border-right: 1px solid #273346; }
QLabel#brand { font-size: 18pt; font-weight: 700; }
QLabel#brandSub { color: #8899af; font-size: 9pt; }
QLabel#eyebrow { color: #7f93ad; font-size: 8pt; font-weight: 700; }
QLabel#title { font-size: 25pt; font-weight: 700; }
QLabel#subtitle { color: #9badc4; font-size: 10pt; }
QLabel#sectionTitle { font-size: 15pt; font-weight: 650; }
QLabel#muted, QLabel#footnote { color: #91a3bb; }
QLabel#footnote { font-size: 8pt; }
QLabel#statValue { font-size: 19pt; font-weight: 700; }
QLabel#statLabel { color: #91a3bb; font-size: 9pt; }
QFrame#stat { background: #172230; border: 1px solid #29374b; border-radius: 10px; }
QFrame#card { background: #192432; border: 1px solid #2c3b50; border-radius: 12px; }
QFrame#card:hover { border-color: #52647b; }
QLabel#cardTitle { font-size: 16pt; font-weight: 700; }
QLabel#console { color: #a4b6ce; font-size: 9pt; }
QLabel#cardNote { color: #a3b2c6; font-size: 9pt; }
QLabel#badge { padding: 3px 8px; border-radius: 5px; font-size: 8pt; }
QLabel#legal { color: #8295ad; font-size: 8pt; }
QLineEdit { background: #172331; border: 1px solid #34465c; border-radius: 8px; padding: 11px 13px; selection-background-color: #267c68; }
QLineEdit:focus { border-color: #62dfb6; }
QComboBox { background: #172331; border: 1px solid #34465c; border-radius: 7px; padding: 8px 12px; min-width: 110px; }
QComboBox QAbstractItemView { background: #172331; color: #edf3fa; selection-background-color: #203e3c; border: 1px solid #34465c; }
QTreeWidget, QListWidget { background: #172331; alternate-background-color: #1b293b; border: 1px solid #34465c; border-radius: 8px; padding: 5px; selection-background-color: #203e3c; }
QTreeWidget::item { padding: 7px 3px; }
QTreeWidget::item:selected, QListWidget::item:selected { background: #203e3c; }
QHeaderView::section { background: #243448; color: #a9bcd5; border: none; border-bottom: 1px solid #3a4c62; padding: 8px; }
QStackedWidget { background: transparent; }
QPushButton { background: #253448; border: 1px solid #3a4c62; border-radius: 7px; padding: 8px 12px; font-weight: 600; }
QPushButton:hover { background: #30435b; border-color: #63758a; }
QPushButton:pressed { background: #1c2939; }
QPushButton:disabled { color: #6f8197; background: #1b2736; border-color: #29374a; }
QPushButton#primary { background: #62dfb6; color: #0e3028; border-color: #62dfb6; }
QPushButton#primary:hover { background: #88edcb; border-color: #88edcb; }
QPushButton#primary:pressed { background: #44cda3; }
QPushButton#primary:disabled { background: #23443e; color: #6a9c8e; border-color: #2c544b; }
QPushButton#quiet { background: transparent; border: none; padding: 5px 4px; color: #a9bcd5; font-size: 9pt; }
QPushButton#quiet:hover { color: #8eefd0; background: #223447; }
QPushButton#quiet:disabled { color: #61758e; background: transparent; }
QFrame#card QPushButton[cardAction="true"] { padding: 8px 9px; font-size: 9pt; }
QPushButton#folderAction { background: transparent; border: 1px solid #3a4c62; padding: 0; border-radius: 7px; }
QPushButton#folderAction:hover { background: #30435b; border-color: #62dfb6; }
QPushButton#folderAction:pressed { background: #203e3c; }
QPushButton#folderAction:disabled { background: #1b2736; border-color: #29374a; }
QPushButton#danger { color: #ffb7af; }
QPushButton#sidebarButton { background: transparent; border: 1px solid #34465c; color: #b1c1d5; }
QPushButton#sidebarButton:hover { background: #253448; }
QListWidget#navigation { border: none; background: transparent; outline: 0; }
QListWidget#navigation::item { border-radius: 7px; margin: 2px 0px; }
QListWidget#navigation::item:selected { background: #203e3c; }
QListWidget#navigation::item:hover:!selected { background: #223045; }
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: #111b29; width: 9px; margin: 0; }
QScrollBar::handle:vertical { background: #43546b; min-height: 35px; border-radius: 4px; }
QScrollBar::handle:vertical:hover { background: #60738c; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
QFrame#operation { background: #18312f; border: 1px solid #365b51; border-radius: 9px; }
QProgressBar { border: none; border-radius: 3px; background: #263d3a; height: 7px; text-align: center; }
QProgressBar::chunk { background: #62dfb6; border-radius: 3px; }
QPlainTextEdit { background: #101a27; border: 1px solid #33455e; border-radius: 8px; padding: 10px; font-family: 'Cascadia Code', 'Consolas'; font-size: 9pt; color: #b7c8dc; }
QCheckBox { spacing: 9px; padding: 5px 0; }
QCheckBox::indicator { width: 18px; height: 18px; border: 1px solid #51647b; border-radius: 4px; background: #1b2a3b; }
QCheckBox::indicator:checked { background: #62dfb6; border: 1px solid #62dfb6; }
QDialogButtonBox QPushButton { min-width: 85px; }
QMessageBox { background: #172230; }
QMenu { background: #192432; border: 1px solid #3a4c62; padding: 5px; }
QMenu::item { padding: 8px 15px; border-radius: 4px; }
QMenu::item:selected { background: #30435b; }
QToolTip { background: #26384e; color: #eef5ff; border: 1px solid #526a88; padding: 7px; }
QStatusBar { color: #8295ad; background: #101722; font-size: 8pt; }
"""
