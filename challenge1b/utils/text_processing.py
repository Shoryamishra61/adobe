import re
import nltk
from nltk.tokenize import sent_tokenize, word_tokenize
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer
import logging

logger = logging.getLogger(__name__)

# Download required NLTK resources
try:
    nltk.download('punkt', quiet=True)
    nltk.download('stopwords', quiet=True)
    nltk.download('wordnet', quiet=True)
except Exception as e:
    logger.warning(f"Failed to download NLTK resources: {e}")

# Initialize lemmatizer
lemmatizer = WordNetLemmatizer()

# Get stopwords
try:
    stop_words = set(stopwords.words('english'))
except Exception as e:
    logger.warning(f"Failed to load stopwords: {e}")
    stop_words = set()

def clean_text(text):
    """Clean text by removing special characters and extra whitespace.
    
    Args:
        text (str): Input text
        
    Returns:
        str: Cleaned text
    """
    if not text or not isinstance(text, str):
        return ""
    
    # Replace newlines with spaces
    text = re.sub(r'\n+', ' ', text)
    
    # Remove special characters and digits
    text = re.sub(r'[^\w\s]', ' ', text)
    
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text

def tokenize_sentences(text):
    """Split text into sentences.
    
    Args:
        text (str): Input text
        
    Returns:
        list: List of sentences
    """
    if not text or not isinstance(text, str):
        return []
    
    try:
        return sent_tokenize(text)
    except Exception as e:
        logger.error(f"Error tokenizing sentences: {e}")
        # Fallback to simple splitting
        return re.split(r'[.!?]+', text)

def preprocess_text(text, remove_stopwords=True, lemmatize=True):
    """Preprocess text for NLP tasks.
    
    Args:
        text (str): Input text
        remove_stopwords (bool): Whether to remove stopwords
        lemmatize (bool): Whether to lemmatize words
        
    Returns:
        str: Preprocessed text
    """
    if not text or not isinstance(text, str):
        return ""
    
    # Clean text
    text = clean_text(text)
    
    # Tokenize
    words = word_tokenize(text.lower())
    
    # Remove stopwords
    if remove_stopwords:
        words = [w for w in words if w not in stop_words]
    
    # Lemmatize
    if lemmatize:
        words = [lemmatizer.lemmatize(w) for w in words]
    
    return ' '.join(words)

def extract_keywords(text, top_n=10):
    """Extract important keywords from text.
    
    Args:
        text (str): Input text
        top_n (int): Number of keywords to extract
        
    Returns:
        list: List of keywords
    """
    if not text or not isinstance(text, str):
        return []
    
    # Preprocess text
    processed_text = preprocess_text(text)
    
    # Tokenize
    words = word_tokenize(processed_text)
    
    # Count word frequencies
    word_freq = {}
    for word in words:
        if len(word) > 2:  # Only consider words with more than 2 characters
            word_freq[word] = word_freq.get(word, 0) + 1
    
    # Sort by frequency
    sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
    
    # Return top N keywords
    return [word for word, freq in sorted_words[:top_n]]

def chunk_text(text, chunk_size=512, overlap=50):
    """Split text into overlapping chunks for processing.
    
    Args:
        text (str): Input text
        chunk_size (int): Maximum chunk size in characters
        overlap (int): Overlap between chunks in characters
        
    Returns:
        list: List of text chunks
    """
    if not text or not isinstance(text, str):
        return []
    
    # Clean text
    text = clean_text(text)
    
    # Split into sentences
    sentences = tokenize_sentences(text)
    
    chunks = []
    current_chunk = ""
    
    for sentence in sentences:
        # If adding this sentence would exceed chunk size, save current chunk and start a new one
        if len(current_chunk) + len(sentence) > chunk_size and current_chunk:
            chunks.append(current_chunk.strip())
            # Start new chunk with overlap from previous chunk
            words = current_chunk.split()
            overlap_text = ' '.join(words[-overlap:]) if len(words) > overlap else current_chunk
            current_chunk = overlap_text + ' ' + sentence
        else:
            current_chunk += ' ' + sentence
    
    # Add the last chunk if it's not empty
    if current_chunk.strip():
        chunks.append(current_chunk.strip())
    
    return chunks