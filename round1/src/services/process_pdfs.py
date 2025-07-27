import fitz
import pdfplumber
import pandas as pd
import re
import json
import statistics
import logging
import concurrent.futures
import os
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from ..config.config import MAX_WORKERS, ENABLE_TABLE_EXTRACTION, ENABLE_OUTLINE_EXTRACTION
from ..utils.cache import cached
from ..utils.text_processing import clean_text, extract_keywords, chunk_text

# Get logger
logger = logging.getLogger(__name__)

class PDFProcessor:
    """Advanced PDF processing class for extracting structured data from PDFs.
    
    This class provides methods to extract tables, outlines, text content, and metadata
    from PDF documents using PyMuPDF (fitz) and pdfplumber.
    """
    
    def __init__(self, pdf_path):
        """Initialize the PDF processor.
        
        Args:
            pdf_path: Path to the PDF file
            
        Raises:
            FileNotFoundError: If the PDF file does not exist
            ValueError: If the file is not a valid PDF
        """
        self.pdf_path = Path(pdf_path)
        if not self.pdf_path.exists():
            raise FileNotFoundError(f"PDF not found at: {self.pdf_path}")
            
        try:
            self.doc = fitz.open(self.pdf_path)
            if not self.doc.is_pdf:
                raise ValueError(f"File is not a valid PDF: {self.pdf_path}")
                
            self.base_font_size = self._get_base_font_size()
            self.metadata = self._extract_metadata()
            self.page_count = len(self.doc)
            
            # Initialize pdfplumber document for table extraction
            self.plumber_doc = None
            
        except Exception as e:
            logger.error(f"Error initializing PDF processor for {self.pdf_path}: {e}")
            raise

    def _get_base_font_size(self) -> int:
        """Determine the most common font size in the document.
        
        Returns:
            int: The most common font size, or 12 if it cannot be determined
        """
        try:
            sizes = [round(s['size']) for p in self.doc for b in p.get_text("dict")["blocks"]
                     if b['type'] == 0 for l in b['lines'] for s in l['spans'] if s['text'].strip()]
            return statistics.mode(sizes) if sizes else 12
        except Exception as e:
            logger.warning(f"Could not determine base font size for {self.pdf_path.name}. Defaulting to 12. Error: {e}")
            return 12
            
    def _extract_metadata(self) -> Dict[str, str]:
        """Extract metadata from the PDF document.
        
        Returns:
            Dict[str, str]: Dictionary containing metadata fields
        """
        metadata = {
            'title': self.doc.metadata.get('title', self.pdf_path.stem),
            'author': self.doc.metadata.get('author', ''),
            'subject': self.doc.metadata.get('subject', ''),
            'keywords': self.doc.metadata.get('keywords', ''),
            'creator': self.doc.metadata.get('creator', ''),
            'producer': self.doc.metadata.get('producer', ''),
            'creation_date': self.doc.metadata.get('creationDate', ''),
            'modification_date': self.doc.metadata.get('modDate', ''),
            'page_count': len(self.doc),
            'file_size': os.path.getsize(self.pdf_path) if self.pdf_path.exists() else 0,
            'file_name': self.pdf_path.name
        }
        return metadata

    @cached
    def extract_tables(self) -> List[Dict[str, Any]]:
        """Extract tables from the PDF document.
        
        Returns:
            List[Dict[str, Any]]: List of extracted tables with page number, index, and data
        """
        if not ENABLE_TABLE_EXTRACTION:
            logger.info(f"Table extraction disabled for {self.pdf_path.name}")
            return []
            
        extracted_tables = []
        try:
            # Lazy initialization of pdfplumber document
            if self.plumber_doc is None:
                self.plumber_doc = pdfplumber.open(self.pdf_path)
                
            # Process each page
            for pno, page in enumerate(self.plumber_doc.pages, 1):
                logger.debug(f"Extracting tables from page {pno} of {self.pdf_path.name}")
                
                try:
                    # Extract tables from the page
                    tables = page.extract_tables()
                    
                    # Process each table
                    for i, table in enumerate(tables):
                        if not table or len(table) < 2:  # Skip empty tables or tables with only headers
                            continue
                            
                        # Try to use the first row as headers
                        headers = table[0]
                        
                        # Check if headers are valid
                        if not all(headers):
                            # If headers contain None or empty strings, generate column names
                            headers = [f"Column_{j+1}" for j in range(len(table[0]))]
                        
                        # Create DataFrame from table data
                        df = pd.DataFrame(table[1:], columns=headers)
                        
                        # Clean column names
                        df.columns = [str(col).strip() for col in df.columns]
                        
                        # Add table to results
                        table_data = {
                            "page": pno,
                            "idx": i + 1,
                            "rows": len(df),
                            "columns": len(df.columns),
                            "headers": df.columns.tolist(),
                            "data": df.to_dict('records')
                        }
                        extracted_tables.append(table_data)
                        
                except Exception as e:
                    logger.warning(f"Error extracting tables from page {pno}: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error extracting tables from {self.pdf_path.name}: {e}")
        
        logger.info(f"Extracted {len(extracted_tables)} tables from {self.pdf_path.name}")
        return extracted_tables

    @cached
    def extract_outline(self) -> List[Dict[str, Any]]:
        """Extract document outline (headings) based on font size and formatting.
        
        Returns:
            List[Dict[str, Any]]: List of headings with level, text, and page number
        """
        if not ENABLE_OUTLINE_EXTRACTION:
            logger.info(f"Outline extraction disabled for {self.pdf_path.name}")
            return []
            
        headings = []
        try:
            # First try to get the document's built-in outline/bookmarks
            toc = self.doc.get_toc()
            if toc:
                logger.info(f"Using built-in outline for {self.pdf_path.name}")
                for level, title, page in toc:
                    headings.append({
                        "level": f"H{min(level, 3)}",  # Limit to H1-H3
                        "text": title,
                        "page": page,
                        "source": "toc"
                    })
                return headings
                
            # If no built-in outline, extract headings based on formatting
            logger.info(f"Extracting outline based on formatting for {self.pdf_path.name}")
            for pno, page in enumerate(self.doc, 1):
                logger.debug(f"Extracting headings from page {pno}")
                
                # Get page text with formatting information
                blocks = page.get_text("dict")["blocks"]
                
                for blk in blocks:
                    # Only process text blocks
                    if blk["type"] != 0 or not blk['lines']:
                        continue
                        
                    # Process each line in the block
                    for line_idx, line in enumerate(blk['lines']):
                        if not line['spans']:
                            continue
                            
                        # Get the first span (text segment) in the line
                        span = line['spans'][0]
                        
                        # Extract text from all spans in the line
                        text = re.sub(r'\s+', ' ', " ".join(s['text'] for s in line['spans'])).strip()
                        if not text:
                            continue
                            
                        # Get formatting information
                        font_size = span['size']
                        font_name = span['font'].lower()
                        is_bold = 'bold' in font_name or span.get('flags', 0) & 2 > 0
                        is_italic = 'italic' in font_name or span.get('flags', 0) & 4 > 0
                        
                        # Determine heading level based on formatting
                        level = None
                        
                        # Potential heading criteria: not too long, and has distinctive formatting
                        if len(text) < 150:
                            if font_size > self.base_font_size * 1.8 or (font_size > self.base_font_size * 1.6 and is_bold):
                                level = "H1"
                            elif font_size > self.base_font_size * 1.4 or (font_size > self.base_font_size * 1.3 and is_bold):
                                level = "H2"
                            elif font_size > self.base_font_size * 1.2 or (font_size > self.base_font_size * 1.1 and is_bold):
                                level = "H3"
                            # Special case: numbered headings like "1.2.3 Title"
                            elif re.match(r'^\d+(\.\d+)*\s+\w+', text) and (is_bold or is_italic):
                                level = "H3"
                                
                        # Add heading to results if identified
                        if level:
                            headings.append({
                                "level": level,
                                "text": text,
                                "page": pno,
                                "font_size": font_size,
                                "is_bold": is_bold,
                                "source": "format"
                            })
                            
        except Exception as e:
            logger.error(f"Error extracting outline from {self.pdf_path.name}: {e}")
            
        logger.info(f"Extracted {len(headings)} headings from {self.pdf_path.name}")
        return headings

    @cached
    def extract_text(self) -> List[Dict[str, Any]]:
        """Extract text content from the PDF document.
        
        Returns:
            List[Dict[str, Any]]: List of text blocks with page number and content
        """
        if not ENABLE_TEXT_EXTRACTION:
            logger.info(f"Text extraction disabled for {self.pdf_path.name}")
            return []
            
        text_blocks = []
        try:
            for pno, page in enumerate(self.doc, 1):
                logger.debug(f"Extracting text from page {pno} of {self.pdf_path.name}")
                
                # Get page text
                text = page.get_text("text")
                if not text.strip():
                    continue
                    
                # Clean and chunk the text
                cleaned_text = clean_text(text)
                chunks = chunk_text(cleaned_text, chunk_size=1000, overlap=100)
                
                # Extract keywords
                keywords = extract_keywords(cleaned_text, top_n=10)
                
                # Add page text to results
                text_blocks.append({
                    "page": pno,
                    "text": cleaned_text,
                    "chunks": chunks,
                    "keywords": keywords,
                    "word_count": len(cleaned_text.split())
                })
                
        except Exception as e:
            logger.error(f"Error extracting text from {self.pdf_path.name}: {e}")
            
        logger.info(f"Extracted text from {len(text_blocks)} pages of {self.pdf_path.name}")
        return text_blocks
        
    def analyze_content(self) -> Dict[str, Any]:
        """Analyze the PDF content to extract insights.
        
        Returns:
            Dict[str, Any]: Analysis results including document statistics and insights
        """
        try:
            # Extract all content
            outline = self.extract_outline()
            tables = self.extract_tables()
            text_blocks = self.extract_text()
            
            # Calculate document statistics
            total_words = sum(block.get("word_count", 0) for block in text_blocks)
            total_tables = len(tables)
            total_headings = len(outline)
            
            # Extract document-wide keywords
            all_text = " ".join(block.get("text", "") for block in text_blocks)
            keywords = extract_keywords(all_text, top_n=20)
            
            # Analyze document structure
            structure = {
                "heading_density": total_headings / max(1, len(text_blocks)),
                "table_density": total_tables / max(1, len(text_blocks)),
                "avg_words_per_page": total_words / max(1, len(text_blocks))
            }
            
            # Compile analysis results
            analysis = {
                "document_type": self._determine_document_type(structure, tables, outline),
                "statistics": {
                    "page_count": self.page_count,
                    "word_count": total_words,
                    "table_count": total_tables,
                    "heading_count": total_headings
                },
                "structure": structure,
                "keywords": keywords
            }
            
            return analysis
            
        except Exception as e:
            logger.error(f"Error analyzing content of {self.pdf_path.name}: {e}")
            return {}
            
    def _determine_document_type(self, structure, tables, outline) -> str:
        """Determine the type of document based on its content and structure.
        
        Args:
            structure: Document structure metrics
            tables: Extracted tables
            outline: Extracted outline
            
        Returns:
            str: Document type classification
        """
        # Simple heuristic classification
        if structure["table_density"] > 0.5:
            return "data_report"
        elif structure["heading_density"] > 0.3:
            return "structured_document"
        elif self.metadata.get("title", "").lower().find("paper") >= 0 or \
             self.metadata.get("title", "").lower().find("research") >= 0:
            return "research_paper"
        elif len(tables) == 0 and structure["avg_words_per_page"] > 300:
            return "text_heavy_document"
        else:
            return "general_document"
    
    @cached
    def extract_all(self) -> Dict[str, Any]:
        """Extract all content and metadata from the PDF document.
        
        Returns:
            Dict[str, Any]: Comprehensive extraction results
        """
        logger.info(f"Starting extraction for {self.pdf_path.name}")
        
        try:
            # Extract content
            title = self.metadata.get('title', self.pdf_path.stem)
            outline = self.extract_outline()
            tables = self.extract_tables()
            text_blocks = self.extract_text()
            
            # Perform content analysis if advanced analytics is enabled
            analysis = None
            if ENABLE_ADVANCED_ANALYTICS:
                analysis = self.analyze_content()
            
            # Compile results
            result = {
                "title": title,
                "metadata": self.metadata,
                "outline": outline,
                "tables": tables,
                "text": text_blocks
            }
            
            # Add analysis if available
            if analysis:
                result["analysis"] = analysis
                
            logger.info(f"Finished extraction for {self.pdf_path.name}")
            return result
            
        except Exception as e:
            logger.error(f"Error in extract_all for {self.pdf_path.name}: {e}")
            # Return partial results if available
            return {
                "title": self.metadata.get('title', self.pdf_path.stem),
                "metadata": self.metadata,
                "error": str(e)
            }
        finally:
            # Ensure resources are released
            self._cleanup()

    def _cleanup(self):
         """Clean up resources to prevent memory leaks."""
         try:
             if hasattr(self, 'doc') and self.doc:
                 self.doc.close()
                 
             if hasattr(self, 'pdfplumber_doc') and self.pdfplumber_doc:
                 self.pdfplumber_doc.close()
                 
             logger.debug(f"Cleaned up resources for {self.pdf_path.name}")
         except Exception as e:
             logger.error(f"Error during cleanup for {self.pdf_path.name}: {e}")

@cached
def extract_and_save(pdf_path, out_dir):
    """Process a PDF file and save the extracted data to a JSON file.
    
    Args:
        pdf_path: Path to the PDF file
        out_dir: Directory to save the output JSON file
        
    Returns:
        Path to the output JSON file or None if processing failed
    """
    logger.info(f"Processing {pdf_path}")
    try:
        processor = PDFProcessor(pdf_path)
        data = processor.extract_all()
        
        # Create output directory if it doesn't exist
        os.makedirs(out_dir, exist_ok=True)
        
        # Save to JSON file
        out_path = Path(out_dir) / f"{Path(pdf_path).stem}.json"
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            
        logger.info(f"Saved extraction results to {out_path}")
        return out_path
    except Exception as e:
        logger.error(f"Error processing {pdf_path}: {e}")
        return None


def batch_process_pdfs(pdf_paths, out_dir, max_workers=None):
    """Process multiple PDF files in parallel.
    
    Args:
        pdf_paths: List of paths to PDF files
        out_dir: Directory to save the output JSON files
        max_workers: Maximum number of worker threads (defaults to config.MAX_WORKERS)
        
    Returns:
        List of paths to the output JSON files
    """
    if max_workers is None:
        max_workers = MAX_WORKERS
        
    logger.info(f"Batch processing {len(pdf_paths)} PDFs with {max_workers} workers")
    results = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all PDF processing tasks
        future_to_pdf = {executor.submit(extract_and_save, pdf_path, out_dir): pdf_path 
                         for pdf_path in pdf_paths}
        
        # Process results as they complete
        for future in concurrent.futures.as_completed(future_to_pdf):
            pdf_path = future_to_pdf[future]
            try:
                result = future.result()
                if result:
                    results.append(result)
            except Exception as e:
                logger.error(f"Exception processing {pdf_path}: {e}")
    
    logger.info(f"Completed batch processing. Successfully processed {len(results)} of {len(pdf_paths)} PDFs")
    return results