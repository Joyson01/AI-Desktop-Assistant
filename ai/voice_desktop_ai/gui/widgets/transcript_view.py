"""
MARUTI Conversation Transcript View.
Provides scrollable chat bubbles for user commands, assistant responses, and system status pills.
"""

from datetime import datetime

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QFrame,
        QHBoxLayout,
        QLabel,
        QScrollArea,
        QSizePolicy,
        QVBoxLayout,
        QWidget,
    )
except ImportError:
    Qt = QFrame = QHBoxLayout = QLabel = QScrollArea = QSizePolicy = QVBoxLayout = QWidget = object

from gui.theme import ThemeColors


class MessageBubble(QFrame):
    """Individual chat bubble widget."""

    def __init__(self, text: str, sender: str = "assistant", timestamp: str = "", parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)

        is_user = sender == "user"
        is_system = sender == "system"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        if not is_system:
            header_layout = QHBoxLayout()
            header_layout.setContentsMargins(0, 0, 0, 0)
            sender_label = QLabel("You" if is_user else "MARUTI")
            sender_label.setStyleSheet(
                f"color: {'#A5B4FC' if is_user else '#38BDF8'}; font-size: 11px; font-weight: 700; text-transform: uppercase;"
            )
            header_layout.addWidget(sender_label)

            if timestamp:
                time_label = QLabel(timestamp)
                time_label.setStyleSheet(f"color: {ThemeColors.TEXT_MUTED}; font-size: 10px;")
                header_layout.addStretch()
                header_layout.addWidget(time_label)

            layout.addLayout(header_layout)

        content_label = QLabel(text)
        content_label.setWordWrap(True)
        content_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        if is_system:
            content_label.setStyleSheet(f"color: {ThemeColors.TEXT_SECONDARY}; font-size: 11px;")
            content_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        else:
            content_label.setStyleSheet(f"color: {ThemeColors.TEXT_PRIMARY}; font-size: 13px; line-height: 1.4;")

        layout.addWidget(content_label)

        # Style according to sender
        if is_user:
            self.setStyleSheet(f"""
                MessageBubble {{
                    background-color: {ThemeColors.USER_BUBBLE_BG};
                    border: 1px solid {ThemeColors.USER_BUBBLE_BORDER};
                    border-radius: 12px;
                }}
            """)
        elif is_system:
            self.setStyleSheet(f"""
                MessageBubble {{
                    background-color: {ThemeColors.SYSTEM_PILL_BG};
                    border: 1px dashed {ThemeColors.BORDER_COLOR};
                    border-radius: 8px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                MessageBubble {{
                    background-color: {ThemeColors.ASSISTANT_BUBBLE_BG};
                    border: 1px solid {ThemeColors.ASSISTANT_BUBBLE_BORDER};
                    border-radius: 12px;
                }}
            """)


class TranscriptView(QScrollArea):
    """Scrollable conversation container holding message bubbles."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self._container = QWidget()
        self._container.setObjectName("TranscriptContainer")
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(16, 16, 16, 16)
        self._layout.setSpacing(12)
        self._layout.addStretch()

        self.setWidget(self._container)

    def add_user_message(self, text: str):
        now = datetime.now().strftime("%H:%M")
        bubble = MessageBubble(text=text, sender="user", timestamp=now)
        wrapper = QHBoxLayout()
        wrapper.setContentsMargins(40, 0, 0, 0)
        wrapper.addStretch()
        wrapper.addWidget(bubble)
        self._layout.insertLayout(self._layout.count() - 1, wrapper)
        self._scroll_to_bottom()

    def add_assistant_message(self, text: str):
        now = datetime.now().strftime("%H:%M")
        bubble = MessageBubble(text=text, sender="assistant", timestamp=now)
        wrapper = QHBoxLayout()
        wrapper.setContentsMargins(0, 0, 40, 0)
        wrapper.addWidget(bubble)
        wrapper.addStretch()
        self._layout.insertLayout(self._layout.count() - 1, wrapper)
        self._scroll_to_bottom()

    def add_system_message(self, text: str):
        bubble = MessageBubble(text=text, sender="system")
        wrapper = QHBoxLayout()
        wrapper.setContentsMargins(20, 0, 20, 0)
        wrapper.addStretch()
        wrapper.addWidget(bubble)
        wrapper.addStretch()
        self._layout.insertLayout(self._layout.count() - 1, wrapper)
        self._scroll_to_bottom()

    def clear(self):
        # Remove all widgets and layouts except the trailing stretch
        while self._layout.count() > 1:
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                while item.layout().count():
                    sub = item.layout().takeAt(0)
                    if sub.widget():
                        sub.widget().deleteLater()

    def _scroll_to_bottom(self):
        v_bar = self.verticalScrollBar()
        if v_bar:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(50, lambda: v_bar.setValue(v_bar.maximum()))

