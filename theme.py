"""Terminal appearance. Business modules contain no Rich markup or styling."""
from rich import box
from rich.theme import Theme

STYLES = {
    "title": "bold cyan",
    "accent": "cyan",
    "muted": "dim",
    "info": "default",
    "success": "green",
    "warning": "yellow",
    "error": "red",
    "border": "bright_black",
}
THEME = Theme(STYLES)
ICONS = {"info": "·", "success": "✓", "warning": "!", "error": "×", "prompt": "›"}
BORDER = box.ROUNDED
TABLE_BORDER = box.SIMPLE
SPINNER = "dots"
LOG_LINES = 8
PAGE_SIZE = 12
REFRESH_PER_SECOND = 8
BAR_STYLE = "bright_black"
BAR_COMPLETE = "cyan"
BAR_FINISHED = "green"
