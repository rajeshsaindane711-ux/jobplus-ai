import logging
from rich.console import Console
from rich.logging import RichHandler

console = Console(safe_box=True)

def setup_logger(name: str = "JobPilot") -> logging.Logger:
    """Configures and returns a rich logger."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True, show_path=False)],
    )
    return logging.getLogger(name)

logger = setup_logger()
