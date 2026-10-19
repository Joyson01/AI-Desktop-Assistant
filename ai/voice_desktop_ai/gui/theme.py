"""
MARUTI Dark Theme & Styling Constants.
Provides modern dark palette colors and Qt stylesheets.
"""


class ThemeColors:
    # Backgrounds
    BG_DARK = "#0F111A"
    BG_SURFACE = "#1A1D2D"
    BG_CARD = "#21253A"
    BG_CARD_HOVER = "#282D46"
    BG_INPUT = "#151824"

    # Borders & Dividers
    BORDER_COLOR = "#2E334D"
    BORDER_FOCUSED = "#6366F1"

    # Primary Accents
    ACCENT = "#6366F1"          # Indigo
    ACCENT_HOVER = "#4F46E5"
    ACCENT_PRESSED = "#4338CA"
    ACCENT_CYAN = "#38BDF8"

    # State Colors
    STATE_IDLE = "#94A3B8"        # Slate Gray
    STATE_LISTENING = "#10B981"   # Emerald Green
    STATE_THINKING = "#0EA5E9"    # Sky Blue
    STATE_EXECUTING = "#F59E0B"   # Amber
    STATE_SPEAKING = "#8B5CF6"    # Violet
    STATE_ERROR = "#EF4444"       # Coral Red

    # Typography
    TEXT_PRIMARY = "#F1F5F9"
    TEXT_SECONDARY = "#94A3B8"
    TEXT_MUTED = "#64748B"
    TEXT_ACCENT = "#818CF8"

    # Message Bubbles
    USER_BUBBLE_BG = "#2B284D"
    USER_BUBBLE_BORDER = "#4F46E5"
    ASSISTANT_BUBBLE_BG = "#1E2235"
    ASSISTANT_BUBBLE_BORDER = "#2E334D"
    SYSTEM_PILL_BG = "#161926"


class ModernDarkTheme:
    """Manages application stylesheet and theme styling."""

    @staticmethod
    def get_stylesheet() -> str:
        return f"""
        QMainWindow {{
            background-color: {ThemeColors.BG_DARK};
            color: {ThemeColors.TEXT_PRIMARY};
            font-family: 'Segoe UI', 'Ubuntu', 'Inter', -apple-system, sans-serif;
            font-size: 13px;
        }}

        QWidget {{
            background-color: transparent;
            color: {ThemeColors.TEXT_PRIMARY};
            font-family: 'Segoe UI', 'Ubuntu', 'Inter', -apple-system, sans-serif;
        }}

        /* Header Bar */
        #HeaderFrame {{
            background-color: {ThemeColors.BG_SURFACE};
            border-bottom: 1px solid {ThemeColors.BORDER_COLOR};
            padding: 8px 16px;
        }}

        #AppTitle {{
            color: {ThemeColors.TEXT_PRIMARY};
            font-size: 18px;
            font-weight: 700;
            letter-spacing: 1px;
        }}

        #AppSubtitle {{
            color: {ThemeColors.TEXT_SECONDARY};
            font-size: 11px;
            font-weight: 400;
        }}

        #StatusLabel {{
            color: {ThemeColors.TEXT_SECONDARY};
            font-size: 12px;
            font-weight: 600;
        }}

        /* Scroll Area & Chat Transcript */
        QScrollArea {{
            background-color: {ThemeColors.BG_DARK};
            border: none;
        }}

        #TranscriptContainer {{
            background-color: {ThemeColors.BG_DARK};
        }}

        QScrollBar:vertical {{
            border: none;
            background: {ThemeColors.BG_DARK};
            width: 8px;
            margin: 0px;
            border-radius: 4px;
        }}

        QScrollBar::handle:vertical {{
            background: {ThemeColors.BORDER_COLOR};
            min-height: 24px;
            border-radius: 4px;
        }}

        QScrollBar::handle:vertical:hover {{
            background: {ThemeColors.ACCENT};
        }}

        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            border: none;
            background: none;
            height: 0px;
        }}

        /* Input Dock Bar */
        #InputDock {{
            background-color: {ThemeColors.BG_SURFACE};
            border-top: 1px solid {ThemeColors.BORDER_COLOR};
            padding: 10px 16px;
        }}

        QLineEdit {{
            background-color: {ThemeColors.BG_INPUT};
            color: {ThemeColors.TEXT_PRIMARY};
            border: 1px solid {ThemeColors.BORDER_COLOR};
            border-radius: 8px;
            padding: 10px 14px;
            font-size: 13px;
            selection-background-color: {ThemeColors.ACCENT};
        }}

        QLineEdit:focus {{
            border: 1.5px solid {ThemeColors.ACCENT};
            background-color: {ThemeColors.BG_INPUT};
        }}

        QLineEdit:disabled {{
            background-color: {ThemeColors.BG_DARK};
            color: {ThemeColors.TEXT_MUTED};
        }}

        /* Buttons */
        QPushButton {{
            background-color: {ThemeColors.BG_CARD};
            color: {ThemeColors.TEXT_PRIMARY};
            border: 1px solid {ThemeColors.BORDER_COLOR};
            border-radius: 8px;
            padding: 8px 16px;
            font-size: 13px;
            font-weight: 500;
        }}

        QPushButton:hover {{
            background-color: {ThemeColors.BG_CARD_HOVER};
            border-color: {ThemeColors.ACCENT};
        }}

        QPushButton:pressed {{
            background-color: {ThemeColors.ACCENT_PRESSED};
        }}

        QPushButton:disabled {{
            background-color: {ThemeColors.BG_DARK};
            color: {ThemeColors.TEXT_MUTED};
            border-color: {ThemeColors.BORDER_COLOR};
        }}

        /* Primary Send Button */
        #SendButton {{
            background-color: {ThemeColors.ACCENT};
            color: #FFFFFF;
            border: none;
            border-radius: 8px;
            font-weight: 600;
            padding: 9px 18px;
        }}

        #SendButton:hover {{
            background-color: {ThemeColors.ACCENT_HOVER};
        }}

        #SendButton:pressed {{
            background-color: {ThemeColors.ACCENT_PRESSED};
        }}

        /* Microphone Toggle Button */
        #MicButton {{
            background-color: {ThemeColors.BG_CARD};
            border: 1px solid {ThemeColors.BORDER_COLOR};
            border-radius: 20px;
            min-width: 40px;
            max-width: 40px;
            min-height: 40px;
            max-height: 40px;
            font-size: 16px;
        }}

        #MicButton:hover {{
            background-color: {ThemeColors.BG_CARD_HOVER};
            border-color: {ThemeColors.ACCENT};
        }}

        #MicButton[listening="true"] {{
            background-color: {ThemeColors.STATE_LISTENING};
            border-color: {ThemeColors.STATE_LISTENING};
            color: #FFFFFF;
        }}

        /* Action Pill / Quick Chips */
        #QuickChip {{
            background-color: {ThemeColors.BG_CARD};
            color: {ThemeColors.TEXT_SECONDARY};
            border: 1px solid {ThemeColors.BORDER_COLOR};
            border-radius: 12px;
            padding: 4px 10px;
            font-size: 11px;
        }}

        #QuickChip:hover {{
            color: {ThemeColors.TEXT_PRIMARY};
            border-color: {ThemeColors.ACCENT};
            background-color: {ThemeColors.BG_CARD_HOVER};
        }}

        /* System Info Pill */
        #SystemPill {{
            background-color: {ThemeColors.SYSTEM_PILL_BG};
            border: 1px solid {ThemeColors.BORDER_COLOR};
            border-radius: 12px;
            color: {ThemeColors.TEXT_MUTED};
            font-size: 11px;
            padding: 4px 12px;
        }}
        """

