import logging
import sys
from pathlib import Path
from ..config.config import LOG_LEVEL, LOG_FORMAT

def setup_logging(log_file=None):
    """Configure logging for the application.
    
    Args:
        log_file (str, optional): Path to log file. If None, logs to console only.
    """
    # Convert string log level to logging constant
    log_level = getattr(logging, LOG_LEVEL.upper())
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Remove existing handlers to avoid duplicate logs
    for handler in root_logger.handlers[:]:  
        root_logger.removeHandler(handler)
    
    # Create formatter
    formatter = logging.Formatter(LOG_FORMAT)
    
    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # Create file handler if log_file is provided
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(log_path, encoding='utf-8')
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    
    # Create application logger
    logger = logging.getLogger('docusphere')
    
    return logger

def get_logger(name):
    """Get a logger with the given name.
    
    Args:
        name (str): Logger name, typically the module name
        
    Returns:
        logging.Logger: Configured logger instance
    """
    return logging.getLogger(f'docusphere.{name}')