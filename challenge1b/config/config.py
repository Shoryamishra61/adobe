# Configuration settings for the application

# Model for sentence transformer
# Model configuration
SENTENCE_TRANSFORMER_MODEL = 'all-MiniLM-L6-v2'

# API configuration
API_VERSION = 'v1'
DEBUG_MODE = False

# Performance settings
BATCH_SIZE = 16
MAX_WORKERS = 4

# Feature flags
ENABLE_CACHING = True
ENABLE_TEXT_EXTRACTION = True
ENABLE_TABLE_EXTRACTION = True
ENABLE_OUTLINE_EXTRACTION = True
ENABLE_ADVANCED_ANALYTICS = True

# Cache settings
CACHE_DIR = 'cache'
CACHE_EXPIRY = 3600  # seconds

# Logging configuration
LOG_LEVEL = 'INFO'
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

# PDF Processing Configuration

# Temporary directory for file processing
TEMP_DIR = 'temp'

# Conversion settings
CONVERSION_FORMATS = ['html', 'docx', 'markdown', 'text', 'epub']
DEFAULT_IMAGE_QUALITY = 90  # 0-100
DEFAULT_IMAGE_DPI = 150

# Redaction settings
REDACTION_PATTERNS = {
    'email': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
    'phone': r'\b(\+\d{1,2}\s)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b',
    'ssn': r'\b\d{3}-\d{2}-\d{4}\b',
    'credit_card': r'\b(?:\d{4}[- ]?){3}\d{4}\b',
    'date': r'\b\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}\b',
    'address': r'\b\d+\s+[A-Za-z0-9\s,]+\b(?:street|st|avenue|ave|road|rd|highway|hwy|square|sq|trail|trl|drive|dr|court|ct|parkway|pkwy|circle|cir|boulevard|blvd)\b',
    'ip_address': r'\b(?:\d{1,3}\.){3}\d{1,3}\b',
    'url': r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+'
}
DEFAULT_REDACTION_TEXT = '[REDACTED]'

# Annotation settings
ANNOTATION_TYPES = ['text', 'highlight', 'underline', 'squiggly', 'strikeout', 'stamp', 'link', 'line', 'rectangle', 'circle', 'polygon', 'ink']
DEFAULT_ANNOTATION_COLOR = '#FF0000'  # Red
DEFAULT_ANNOTATION_OPACITY = 0.5

# Watermark settings
WATERMARK_POSITIONS = ['center', 'diagonal', 'tiled', 'custom']
DEFAULT_WATERMARK_OPACITY = 0.3
DEFAULT_WATERMARK_ROTATION = 45  # degrees
DEFAULT_WATERMARK_FONT = 'Helvetica'
DEFAULT_WATERMARK_FONT_SIZE = 24
DEFAULT_WATERMARK_COLOR = '#888888'  # Gray

# Compression settings
COMPRESSION_LEVELS = {
    'low': {'image_quality': 85, 'image_dpi': 150},
    'medium': {'image_quality': 75, 'image_dpi': 120},
    'high': {'image_quality': 60, 'image_dpi': 96},
    'extreme': {'image_quality': 40, 'image_dpi': 72}
}

# Security settings
ENCRYPTION_LEVELS = [40, 128, 256]  # bits
DEFAULT_ENCRYPTION_LEVEL = 128

# Optimization profiles
OPTIMIZATION_PROFILES = {
    'web': {
        'image_quality': 75,
        'image_dpi': 96,
        'image_downsampling': 'bicubic',
        'color_space': 'rgb',
        'compress_text': True,
        'flatten_transparency': True,
        'remove_unused_objects': True,
        'remove_metadata': False,
        'linearize': True
    },
    'print': {
        'image_quality': 90,
        'image_dpi': 300,
        'image_downsampling': 'bicubic',
        'color_space': 'cmyk',
        'compress_text': True,
        'flatten_transparency': False,
        'remove_unused_objects': True,
        'remove_metadata': False,
        'linearize': False
    },
    'ebook': {
        'image_quality': 80,
        'image_dpi': 150,
        'image_downsampling': 'bicubic',
        'color_space': 'rgb',
        'compress_text': True,
        'flatten_transparency': True,
        'remove_unused_objects': True,
        'remove_metadata': False,
        'linearize': True
    },
    'balanced': {
        'image_quality': 85,
        'image_dpi': 200,
        'image_downsampling': 'bicubic',
        'color_space': 'rgb',
        'compress_text': True,
        'flatten_transparency': True,
        'remove_unused_objects': True,
        'remove_metadata': False,
        'linearize': True
    }
}

# OCR settings
OCR_LANGUAGES = ['eng', 'spa', 'fra', 'deu', 'ita', 'por', 'rus', 'chi_sim', 'jpn', 'kor']
DEFAULT_OCR_LANGUAGE = 'eng'
OCR_OUTPUT_FORMATS = ['text', 'json', 'markdown', 'html', 'hocr']
DEFAULT_OCR_DPI = 300

# Validation standards
VALIDATION_STANDARDS = ['pdf/a-1b', 'pdf/a-2b', 'pdf/a-3b', 'pdf/ua-1', 'pdf/x-1a', 'pdf/x-3', 'pdf/x-4']
DEFAULT_VALIDATION_STANDARD = 'pdf/a-2b'