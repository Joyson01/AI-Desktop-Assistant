"""
MARUTI Animated Status Orb Widget.
Displays the current state of the assistant (Idle, Listening, Thinking, Executing, Speaking, Error)
with smooth glowing and pulsing effects using QPainter.
"""

from enum import Enum
import math

try:
    from PySide6.QtCore import QPointF, QRectF, QTimer, Qt
    from PySide6.QtGui import QBrush, QColor, QPainter, QRadialGradient
    from PySide6.QtWidgets import QWidget
except ImportError:
    # Fallback for environments where PySide6 is still installing or mocked
    QPointF = QRectF = QTimer = Qt = object
    QBrush = QColor = QPainter = QRadialGradient = object
    QWidget = object

from gui.theme import ThemeColors


class AssistantState(str, Enum):
    IDLE = "Idle"
    LISTENING = "Listening"
    THINKING = "Thinking"
    EXECUTING = "Executing"
    SPEAKING = "Speaking"
    ERROR = "Error"


STATE_COLOR_MAP = {
    AssistantState.IDLE: ThemeColors.STATE_IDLE,
    AssistantState.LISTENING: ThemeColors.STATE_LISTENING,
    AssistantState.THINKING: ThemeColors.STATE_THINKING,
    AssistantState.EXECUTING: ThemeColors.STATE_EXECUTING,
    AssistantState.SPEAKING: ThemeColors.STATE_SPEAKING,
    AssistantState.ERROR: ThemeColors.STATE_ERROR,
}


class StatusOrb(QWidget):
    """
    Circular animated status indicator widget.
    Pulses smoothly when active and stays steady when idle.
    """

    def __init__(self, parent=None, size: int = 50):
        super().__init__(parent)
        self._size = size
        self.setFixedSize(size, size)
        self._state = AssistantState.IDLE
        self._primary_color = QColor(ThemeColors.STATE_IDLE)
        self._phase = 0.0
        self._pulse_scale = 1.0

        # Animation timer (approx 30 FPS for smooth pulse without CPU strain)
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(33)
        self._anim_timer.timeout.connect(self._on_tick)

    @property
    def state(self) -> AssistantState:
        return self._state

    def set_state(self, state: AssistantState | str):
        if isinstance(state, str):
            try:
                state = AssistantState(state)
            except ValueError:
                state = AssistantState.IDLE
        self._state = state
        hex_color = STATE_COLOR_MAP.get(state, ThemeColors.STATE_IDLE)
        self._primary_color = QColor(hex_color)

        if self._state in {AssistantState.LISTENING, AssistantState.THINKING, AssistantState.SPEAKING, AssistantState.EXECUTING}:
            if not self._anim_timer.isActive():
                self._anim_timer.start()
        else:
            self._anim_timer.stop()
            self._pulse_scale = 1.0
            self._phase = 0.0

        self.update()

    def _on_tick(self):
        # Sine wave breathing pulse
        speed = 0.12 if self._state == AssistantState.LISTENING else 0.08
        self._phase += speed
        if self._phase > 2 * math.pi:
            self._phase -= 2 * math.pi
        self._pulse_scale = 0.85 + 0.15 * math.sin(self._phase)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        center_x = self.width() / 2.0
        center_y = self.height() / 2.0
        center = QPointF(center_x, center_y)
        base_radius = (min(self.width(), self.height()) / 2.0) - 4.0

        # Dynamic radius based on pulse
        pulsed_radius = base_radius * self._pulse_scale

        # Outer Glow Radial Gradient
        glow_gradient = QRadialGradient(center, pulsed_radius * 1.25)
        glow_color = QColor(self._primary_color)
        glow_color.setAlpha(80 if self._state != AssistantState.IDLE else 25)
        fade_color = QColor(self._primary_color)
        fade_color.setAlpha(0)

        glow_gradient.setColorAt(0.0, glow_color)
        glow_gradient.setColorAt(0.7, glow_color)
        glow_gradient.setColorAt(1.0, fade_color)

        painter.setBrush(QBrush(glow_gradient))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(center, pulsed_radius * 1.2, pulsed_radius * 1.2)

        # Inner Solid Orb with highlight
        inner_gradient = QRadialGradient(QPointF(center_x - pulsed_radius * 0.25, center_y - pulsed_radius * 0.25), pulsed_radius)
        highlight_color = self._primary_color.lighter(135)
        inner_gradient.setColorAt(0.0, highlight_color)
        inner_gradient.setColorAt(0.8, self._primary_color)
        inner_gradient.setColorAt(1.0, self._primary_color.darker(120))

        painter.setBrush(QBrush(inner_gradient))
        painter.drawEllipse(center, pulsed_radius * 0.72, pulsed_radius * 0.72)

        # Center Core Dot
        core_color = QColor(255, 255, 255, 180)
        painter.setBrush(QBrush(core_color))
        core_radius = max(2.5, pulsed_radius * 0.18)
        painter.drawEllipse(center, core_radius, core_radius)

        painter.end()

