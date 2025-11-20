"""
Centralized logging configuration for the application.
"""
import logging
import sys
import os  # Import os for directory creation
from pythonjsonlogger import json  # Library for JSON formatting


# --- This filter is new ---
class InfoFilter(logging.Filter):
    """
    A custom filter to *only* allow logs that are
    BELOW the ERROR level (e.g., DEBUG, INFO, WARNING).
    """

    def filter(self, record):
        return record.levelno < logging.ERROR


def setup_logging():
    """
    Configures the root logger for production-style centralized logging (JSON to Console)
    and local file logging (text to logs/ directory).
    """
    # 1. Define the log directory and ensure it exists
    log_dir = "logs"
    # THIS IS THE CRITICAL LINE THAT WAS MISSING/FAILING
    try:
        os.makedirs(log_dir, exist_ok=True)
    except OSError as e:
        # Fallback if we can't create the directory (e.g. permission issue)
        print(f"Warning: Could not create log directory {log_dir}: {e}")
        # In testing, we might not want to fail just because of logs
        pass

    # 2. Define formatters
    # Standard text format for local file logging
    text_formatter = logging.Formatter(
        "%(asctime)s - [%(levelname)s] - %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # JSON format for console/stdout logging (for Docker/OpenSearch/Datadog)
    json_formatter = json.JsonFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(module)s %(funcName)s %(lineno)d %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 3. Get the root logger and set minimum level
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.handlers = []  # Clear existing handlers if called multiple times

    # 4. Console Handler (JSON for Docker/Centralized Logging)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(json_formatter)
    logger.addHandler(console_handler)

    # 5. File Handler (Text for Local Debugging - app.log)
    try:
        app_log_path = os.path.join(log_dir, "app.log")
        app_log_handler = logging.FileHandler(app_log_path)
        app_log_handler.setLevel(logging.INFO)
        app_log_handler.setFormatter(text_formatter)
        logger.addHandler(app_log_handler)
    except (OSError, FileNotFoundError):
        print(
            f"Warning: Could not open log file {app_log_path}. Skipping file logging."
        )

    # 6. Error File Handler (Text for Local Debugging - error.log)
    try:
        error_log_path = os.path.join(log_dir, "error.log")
        error_log_handler = logging.FileHandler(error_log_path)
        error_log_handler.setLevel(logging.ERROR)
        error_log_handler.setFormatter(text_formatter)
        logger.addHandler(error_log_handler)
    except (OSError, FileNotFoundError):
        pass

    # 7. Suppress verbose external module logs
    logging.getLogger("boto3").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)
    # Suppress FastAPI's default logging to avoid duplicate console output
    logging.getLogger("uvicorn").handlers = []
    logging.getLogger("uvicorn.access").handlers = []

    logger.info(
        "Logging configured. JSON output to console/Docker, text output to logs/ directory."
    )
