"""
Centralized logging configuration for the application.
"""
import logging
import sys

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
    Configures the root logger to split logs into different files.
    - app.log: Contains INFO, WARNING, ERROR, CRITICAL
    - error.log: Contains ONLY ERROR, CRITICAL
    - console: Contains INFO and above
    """
    # Create a formatter
    log_format = "%(asctime)s - [%(levelname)s] - %(name)s: %(message)s"
    formatter = logging.Formatter(log_format, datefmt="%Y-%m-%d %H:%M:%S")

    # Get the root logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO) 

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    app_log_handler = logging.FileHandler("logs/app.log")
    app_log_handler.setLevel(logging.INFO)
    app_log_handler.setFormatter(formatter)

    error_log_handler = logging.FileHandler("logs/error.log")
    error_log_handler.setLevel(logging.ERROR) 
    error_log_handler.setFormatter(formatter)
    
    logger.handlers = [console_handler, app_log_handler, error_log_handler]

    logging.getLogger("boto3").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)

    logger.info("Logging configured (split-file setup).")