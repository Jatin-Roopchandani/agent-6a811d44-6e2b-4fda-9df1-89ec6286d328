import logging
import os


def get_tool_logger(name):
    logger = logging.getLogger(name)

    # Clear existing handlers to avoid duplicates
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    # Always add console/stream handler
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    # Only add file handler if PATCHED_LOGGING environment variable is set
    if os.getenv("PATCHED_LOGGING", "false").lower() == "true":
        log_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "logs"))
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        log_file = os.path.join(log_dir, f"patched_adk.tools.log")
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    logger.setLevel(logging.DEBUG)
    return logger
