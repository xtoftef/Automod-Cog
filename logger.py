import logging
import os
import sys
from config import TEST

# Base namespace logger for your system
automod_logger = logging.getLogger("automod")
automod_logger.addHandler(logging.NullHandler())


def setup_automod_logging(is_dev: bool = TEST):
    """Configures the 'automod' logger namespace without interfering with host bot loggers."""
    log_level = logging.DEBUG if is_dev else logging.INFO
    automod_logger.setLevel(log_level)

    # Avoid adding duplicate handlers if the cog is reloaded
    if not automod_logger.handlers or isinstance(
        automod_logger.handlers[0], logging.NullHandler
    ):
        automod_logger.handlers.clear()

        # Terminal output
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        automod_logger.addHandler(stream_handler)

        # File output for dev testing
        if is_dev:
            file_handler = logging.FileHandler(
                "automod_debug.log", mode="a", encoding="utf-8"
            )
            file_handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
            )
            automod_logger.addHandler(file_handler)


def get_logger(module_name: str) -> logging.Logger:
    """Helper to return a child logger under the 'automod' namespace."""
    return logging.getLogger(f"automod.{module_name}")