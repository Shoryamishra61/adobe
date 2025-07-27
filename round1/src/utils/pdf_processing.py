import os
import re
import json
import uuid
import tempfile
from pathlib import Path
from typing import List, Dict, Any, Optional, Union, Tuple
import logging

# Import PDF processing libraries
import fitz  # PyMuPDF
import pdfplumber

# Import configuration
from ..config.config import (
    DEFAULT_IMAGE_QUALITY,
    DEFAULT_IMAGE_DPI,
    REDACTION_PATTERNS,
    DEFAULT_REDACTION_TEXT,
    ANNOTATION_TYPES,
    DEFAULT_ANNOTATION_COLOR,
    DEFAULT_ANNOTATION_OPACITY,
    WATERMARK_POSITIONS,
    DEFAULT_WATERMARK_OPACITY,
    DEFAULT_WATERMARK_ROTATION,
    DEFAULT_WATERMARK_FONT,
    DEFAULT_WATERMARK_FONT_SIZE,
    DEFAULT_WATERMARK_COLOR,
    COMPRESSION_LEVELS,
    ENCRYPTION_LEVELS,
    DEFAULT_ENCRYPTION_LEVEL,
    OPTIMIZATION_PROFILES,
    OCR_LANGUAGES,
    DEFAULT_OCR_LANGUAGE,
    OCR_OUTPUT_FORMATS,
    DEFAULT_OCR_DPI,
    VALIDATION_STANDARDS,
    DEFAULT_VALIDATION_STANDARD
)

# Get logger
logger = logging.getLogger(__name__)

class PDFProcessingError(Exception):
    """Exception raised for errors in PDF processing."""
    pass

class PDFUtility:
    """Utility class for PDF processing operations."""
    
    @staticmethod
    def validate_pdf(file_path: Union[str, Path]) -> bool:
        """Validate if a file is a valid PDF.
        
        Args:
            file_path: Path to the PDF file
            
        Returns:
            bool: True if the file is a valid PDF, False otherwise
        """
        try:
            doc = fitz.open(file_path)
            is_valid = doc.is_pdf
            doc.close()
            return is_valid
        except Exception as e:
            logger.error(f"Error validating PDF {file_path}: {e}")
            return False
    
    @staticmethod
    def extract_metadata(file_path: Union[str, Path]) -> Dict[str, Any]:
        """Extract metadata from a PDF file.
        
        Args:
            file_path: Path to the PDF file
            
        Returns:
            Dict: Dictionary containing metadata fields
        """
        try:
            doc = fitz.open(file_path)
            metadata = {
                'title': doc.metadata.get('title', Path(file_path).stem),
                'author': doc.metadata.get('author', ''),
                'subject': doc.metadata.get('subject', ''),
                'keywords': doc.metadata.get('keywords', ''),
                'creator': doc.metadata.get('creator', ''),
                'producer': doc.metadata.get('producer', ''),
                'creation_date': doc.metadata.get('creationDate', ''),
                'modification_date': doc.metadata.get('modDate', ''),
                'page_count': len(doc),
                'file_size': os.path.getsize(file_path) if os.path.exists(file_path) else 0,
                'file_name': Path(file_path).name
            }
            doc.close()
            return metadata
        except Exception as e:
            logger.error(f"Error extracting metadata from {file_path}: {e}")
            raise PDFProcessingError(f"Failed to extract metadata: {e}")
    
    @staticmethod
    def convert_to_html(file_path: Union[str, Path], include_images: bool = True, 
                       preserve_layout: bool = True, page_range: Optional[List[int]] = None) -> str:
        """Convert PDF to HTML.
        
        Args:
            file_path: Path to the PDF file
            include_images: Whether to include images in the output
            preserve_layout: Whether to preserve the original layout
            page_range: List of page numbers to convert (1-indexed)
            
        Returns:
            str: HTML content
        """
        try:
            doc = fitz.open(file_path)
            
            # Determine which pages to convert
            if page_range:
                # Convert 1-indexed page numbers to 0-indexed
                pages = [p-1 for p in page_range if 1 <= p <= len(doc)]
            else:
                pages = range(len(doc))
            
            html_parts = []
            html_parts.append("<!DOCTYPE html>\n<html>\n<head>\n<meta charset='utf-8'>\n<title>")
            html_parts.append(doc.metadata.get('title', Path(file_path).stem))
            html_parts.append("</title>\n<style>\n")
            
            # Add CSS for layout preservation if requested
            if preserve_layout:
                html_parts.append("""
                .pdf-page { position: relative; margin-bottom: 20px; border: 1px solid #ddd; }
                .pdf-text { position: absolute; }
                .pdf-image { position: absolute; }
                """)
            
            html_parts.append("</style>\n</head>\n<body>\n")
            
            for page_idx in pages:
                page = doc[page_idx]
                html_parts.append(f"<div class='pdf-page' id='page-{page_idx+1}'>\n")
                
                # Get page text with positioning information
                if preserve_layout:
                    text_dict = page.get_text("dict")
                    for block in text_dict.get("blocks", []):
                        if block.get("type") == 0:  # Text block
                            for line in block.get("lines", []):
                                for span in line.get("spans", []):
                                    text = span.get("text", "").replace("<", "&lt;").replace(">", "&gt;")
                                    if text.strip():
                                        x0, y0 = span.get("origin", (0, 0))
                                        font_size = span.get("size", 12)
                                        font_name = span.get("font", "")
                                        color = span.get("color", 0)
                                        style = f"left:{x0}px;top:{y0}px;font-size:{font_size}px;font-family:'{font_name}';color:#{color:06x};"
                                        html_parts.append(f"<div class='pdf-text' style='{style}'>{text}</div>\n")
                else:
                    # Simple text extraction without layout preservation
                    text = page.get_text("text")
                    html_parts.append(f"<pre>{text}</pre>\n")
                
                # Extract and embed images if requested
                if include_images:
                    img_list = page.get_images(full=True)
                    for img_idx, img_info in enumerate(img_list):
                        xref = img_info[0]
                        base_image = doc.extract_image(xref)
                        if base_image:
                            image_bytes = base_image["image"]
                            image_ext = base_image["ext"]
                            import base64
                            img_b64 = base64.b64encode(image_bytes).decode('utf-8')
                            if preserve_layout:
                                # Get image position and size
                                # This is simplified and may not be accurate for all PDFs
                                rect = page.get_image_bbox(img_info)
                                style = f"left:{rect.x0}px;top:{rect.y0}px;width:{rect.width}px;height:{rect.height}px;"
                                html_parts.append(f"<img class='pdf-image' style='{style}' src='data:image/{image_ext};base64,{img_b64}' />\n")
                            else:
                                html_parts.append(f"<img src='data:image/{image_ext};base64,{img_b64}' />\n")
                
                html_parts.append("</div>\n")
            
            html_parts.append("</body>\n</html>")
            doc.close()
            
            return "".join(html_parts)
        except Exception as e:
            logger.error(f"Error converting PDF to HTML {file_path}: {e}")
            raise PDFProcessingError(f"Failed to convert PDF to HTML: {e}")
    
    @staticmethod
    def convert_to_markdown(file_path: Union[str, Path], include_images: bool = True,
                           page_range: Optional[List[int]] = None) -> str:
        """Convert PDF to Markdown.
        
        Args:
            file_path: Path to the PDF file
            include_images: Whether to include images in the output
            page_range: List of page numbers to convert (1-indexed)
            
        Returns:
            str: Markdown content
        """
        try:
            doc = fitz.open(file_path)
            
            # Determine which pages to convert
            if page_range:
                # Convert 1-indexed page numbers to 0-indexed
                pages = [p-1 for p in page_range if 1 <= p <= len(doc)]
            else:
                pages = range(len(doc))
            
            md_parts = []
            
            # Add document title
            title = doc.metadata.get('title', Path(file_path).stem)
            md_parts.append(f"# {title}\n\n")
            
            # Process each page
            for page_idx in pages:
                page = doc[page_idx]
                md_parts.append(f"## Page {page_idx+1}\n\n")
                
                # Extract text
                text = page.get_text("text")
                
                # Basic formatting improvements
                # Replace multiple newlines with double newlines for Markdown paragraphs
                text = re.sub(r'\n{3,}', '\n\n', text)
                
                # Try to detect headings based on font size
                blocks = page.get_text("dict")["blocks"]
                for block in blocks:
                    if block.get("type") == 0:  # Text block
                        for line in block.get("lines", []):
                            for span in line.get("spans", []):
                                span_text = span.get("text", "").strip()
                                if span_text and len(span_text) < 100:  # Potential heading
                                    font_size = span.get("size", 0)
                                    if font_size > 14:  # Likely a heading
                                        # Replace the text with a Markdown heading
                                        heading_level = 2 if font_size > 18 else 3
                                        text = text.replace(span_text, f"\n{'#' * heading_level} {span_text}\n")
                
                md_parts.append(text + "\n\n")
                
                # Extract and include images if requested
                if include_images:
                    img_list = page.get_images(full=True)
                    for img_idx, img_info in enumerate(img_list):
                        xref = img_info[0]
                        base_image = doc.extract_image(xref)
                        if base_image:
                            # Save image to a temporary file
                            image_bytes = base_image["image"]
                            image_ext = base_image["ext"]
                            temp_dir = tempfile.gettempdir()
                            img_filename = f"image_p{page_idx+1}_{img_idx+1}.{image_ext}"
                            img_path = os.path.join(temp_dir, img_filename)
                            
                            with open(img_path, "wb") as img_file:
                                img_file.write(image_bytes)
                            
                            # Add image reference to Markdown
                            md_parts.append(f"![Image {img_idx+1} on page {page_idx+1}]({img_path})\n\n")
            
            doc.close()
            return "".join(md_parts)
        except Exception as e:
            logger.error(f"Error converting PDF to Markdown {file_path}: {e}")
            raise PDFProcessingError(f"Failed to convert PDF to Markdown: {e}")
    
    @staticmethod
    def convert_to_text(file_path: Union[str, Path], page_range: Optional[List[int]] = None) -> str:
        """Convert PDF to plain text.
        
        Args:
            file_path: Path to the PDF file
            page_range: List of page numbers to convert (1-indexed)
            
        Returns:
            str: Plain text content
        """
        try:
            doc = fitz.open(file_path)
            
            # Determine which pages to convert
            if page_range:
                # Convert 1-indexed page numbers to 0-indexed
                pages = [p-1 for p in page_range if 1 <= p <= len(doc)]
            else:
                pages = range(len(doc))
            
            text_parts = []
            
            for page_idx in pages:
                page = doc[page_idx]
                text = page.get_text("text")
                text_parts.append(f"--- Page {page_idx+1} ---\n{text}\n\n")
            
            doc.close()
            return "".join(text_parts)
        except Exception as e:
            logger.error(f"Error converting PDF to text {file_path}: {e}")
            raise PDFProcessingError(f"Failed to convert PDF to text: {e}")
    
    @staticmethod
    def redact_pdf(file_path: Union[str, Path], patterns: Dict[str, str] = None, 
                  redact_types: List[str] = None, custom_regex: str = None,
                  replacement_text: str = DEFAULT_REDACTION_TEXT) -> Tuple[str, Dict[str, Any]]:
        """Redact sensitive information from a PDF.
        
        Args:
            file_path: Path to the PDF file
            patterns: Dictionary of pattern names and regex patterns
            redact_types: List of predefined pattern types to redact
            custom_regex: Custom regex pattern to use for redaction
            replacement_text: Text to replace redacted content with
            
        Returns:
            Tuple[str, Dict]: Path to redacted PDF and redaction summary
        """
        try:
            # Use default patterns if none provided
            if patterns is None:
                patterns = {}
            
            # Add predefined patterns based on redact_types
            if redact_types:
                for pattern_type in redact_types:
                    if pattern_type in REDACTION_PATTERNS:
                        patterns[pattern_type] = REDACTION_PATTERNS[pattern_type]
            
            # Add custom regex if provided
            if custom_regex:
                patterns['custom'] = custom_regex
            
            # If no patterns specified, use all predefined patterns
            if not patterns:
                patterns = REDACTION_PATTERNS
            
            # Open the PDF
            doc = fitz.open(file_path)
            
            # Initialize redaction summary
            summary = {
                'original_file': Path(file_path).name,
                'page_count': len(doc),
                'total_redactions': 0,
                'patterns_used': list(patterns.keys()),
                'redactions_by_type': {k: 0 for k in patterns.keys()},
                'redactions_by_page': {}
            }
            
            # Process each page
            for page_idx in range(len(doc)):
                page = doc[page_idx]
                page_text = page.get_text("text")
                page_redactions = 0
                
                # Apply each pattern
                for pattern_name, pattern in patterns.items():
                    matches = re.finditer(pattern, page_text)
                    for match in matches:
                        # Get match coordinates
                        match_text = match.group(0)
                        instances = page.search_for(match_text)
                        
                        for inst in instances:
                            # Add redaction annotation
                            page.add_redact_annot(inst, replacement_text)
                            
                            # Update counters
                            summary['total_redactions'] += 1
                            summary['redactions_by_type'][pattern_name] = summary['redactions_by_type'].get(pattern_name, 0) + 1
                            page_redactions += 1
                
                # Apply redactions
                page.apply_redactions()
                
                # Update page summary
                if page_redactions > 0:
                    summary['redactions_by_page'][str(page_idx + 1)] = page_redactions
            
            # Save redacted PDF
            output_path = f"{Path(file_path).stem}_redacted.pdf"
            doc.save(output_path)
            doc.close()
            
            return output_path, summary
        except Exception as e:
            logger.error(f"Error redacting PDF {file_path}: {e}")
            raise PDFProcessingError(f"Failed to redact PDF: {e}")
    
    @staticmethod
    def add_watermark(file_path: Union[str, Path], watermark_type: str, 
                     watermark_text: str = None, watermark_image: str = None,
                     watermark_pdf: str = None, position: str = 'center',
                     opacity: float = DEFAULT_WATERMARK_OPACITY, 
                     rotation: int = DEFAULT_WATERMARK_ROTATION,
                     scale: float = 1.0, x_position: int = None, y_position: int = None,
                     page_range: str = 'all', custom_pages: List[int] = None,
                     font: str = DEFAULT_WATERMARK_FONT, 
                     font_size: int = DEFAULT_WATERMARK_FONT_SIZE,
                     font_color: str = DEFAULT_WATERMARK_COLOR) -> Tuple[str, Dict[str, Any]]:
        """Add watermark to a PDF.
        
        Args:
            file_path: Path to the PDF file
            watermark_type: Type of watermark ('text', 'image', or 'pdf')
            watermark_text: Text to use as watermark
            watermark_image: Path to image to use as watermark
            watermark_pdf: Path to PDF to use as watermark
            position: Watermark position ('center', 'diagonal', 'tiled', 'custom')
            opacity: Watermark opacity (0.0-1.0)
            rotation: Watermark rotation in degrees
            scale: Watermark scale factor
            x_position: Custom X position (if position is 'custom')
            y_position: Custom Y position (if position is 'custom')
            page_range: Page range ('all', 'even', 'odd', 'custom')
            custom_pages: List of page numbers for custom page range
            font: Font for text watermark
            font_size: Font size for text watermark
            font_color: Font color for text watermark (hex code)
            
        Returns:
            Tuple[str, Dict]: Path to watermarked PDF and watermark summary
        """
        try:
            # Validate watermark type and required parameters
            if watermark_type == 'text' and not watermark_text:
                raise ValueError("Text watermark requires 'watermark_text' parameter")
            elif watermark_type == 'image' and not watermark_image:
                raise ValueError("Image watermark requires 'watermark_image' parameter")
            elif watermark_type == 'pdf' and not watermark_pdf:
                raise ValueError("PDF watermark requires 'watermark_pdf' parameter")
            
            # Open the PDF
            doc = fitz.open(file_path)
            
            # Determine which pages to watermark
            pages_to_watermark = []
            if page_range == 'all':
                pages_to_watermark = list(range(len(doc)))
            elif page_range == 'even':
                pages_to_watermark = [i for i in range(len(doc)) if (i + 1) % 2 == 0]
            elif page_range == 'odd':
                pages_to_watermark = [i for i in range(len(doc)) if (i + 1) % 2 == 1]
            elif page_range == 'custom' and custom_pages:
                # Convert 1-indexed page numbers to 0-indexed
                pages_to_watermark = [p - 1 for p in custom_pages if 1 <= p <= len(doc)]
            
            # Prepare watermark
            if watermark_type == 'text':
                # Create a temporary PDF with the text watermark
                watermark_doc = fitz.open()
                watermark_page = watermark_doc.new_page(width=612, height=792)  # Letter size
                
                # Convert hex color to RGB tuple
                color_hex = font_color.lstrip('#')
                color_rgb = tuple(int(color_hex[i:i+2], 16) / 255 for i in (0, 2, 4))
                
                # Add text to watermark page
                text_rect = fitz.Rect(0, 0, 612, 792)
                watermark_page.insert_text(
                    text_rect.center,  # Center of page
                    watermark_text,
                    fontname=font,
                    fontsize=font_size,
                    rotate=rotation,
                    color=color_rgb,
                    alpha=opacity
                )
                
            elif watermark_type == 'image':
                # Create a temporary PDF with the image watermark
                watermark_doc = fitz.open()
                watermark_page = watermark_doc.new_page(width=612, height=792)  # Letter size
                
                # Add image to watermark page
                img_rect = fitz.Rect(100, 100, 512, 692)  # Adjust as needed
                watermark_page.insert_image(img_rect, filename=watermark_image, alpha=opacity, rotate=rotation)
                
            elif watermark_type == 'pdf':
                # Use existing PDF as watermark
                watermark_doc = fitz.open(watermark_pdf)
            
            # Apply watermark to selected pages
            for page_idx in pages_to_watermark:
                page = doc[page_idx]
                
                # Get watermark page (first page if watermark is a PDF)
                wm_page = watermark_doc[0] if watermark_type in ['text', 'image'] else watermark_doc[0 % len(watermark_doc)]
                
                # Determine watermark position
                if position == 'center':
                    # Center watermark on page
                    page.show_pdf_page(
                        page.rect.center,  # Center point
                        watermark_doc,
                        0,  # First page of watermark
                        alpha=opacity,
                        rotate=rotation,
                        scale=scale
                    )
                elif position == 'diagonal':
                    # Place watermark diagonally across page
                    page.show_pdf_page(
                        page.rect.center,  # Center point
                        watermark_doc,
                        0,  # First page of watermark
                        alpha=opacity,
                        rotate=45,  # Diagonal
                        scale=scale
                    )
                elif position == 'tiled':
                    # Tile watermark across page
                    tile_size = 200 * scale  # Adjust as needed
                    for x in range(0, int(page.rect.width), int(tile_size)):
                        for y in range(0, int(page.rect.height), int(tile_size)):
                            page.show_pdf_page(
                                fitz.Point(x, y),
                                watermark_doc,
                                0,  # First page of watermark
                                alpha=opacity,
                                rotate=rotation,
                                scale=scale * 0.5  # Smaller for tiling
                            )
                elif position == 'custom' and x_position is not None and y_position is not None:
                    # Custom position
                    page.show_pdf_page(
                        fitz.Point(x_position, y_position),
                        watermark_doc,
                        0,  # First page of watermark
                        alpha=opacity,
                        rotate=rotation,
                        scale=scale
                    )
            
            # Close watermark document
            if watermark_type in ['text', 'image']:
                watermark_doc.close()
            
            # Save watermarked PDF
            output_path = f"{Path(file_path).stem}_watermarked.pdf"
            doc.save(output_path)
            
            # Prepare summary
            summary = {
                'original_file': Path(file_path).name,
                'watermarked_file': Path(output_path).name,
                'page_count': len(doc),
                'watermark_type': watermark_type,
                'position': position,
                'opacity': opacity,
                'rotation': rotation,
                'scale': scale,
                'page_range': page_range,
                'watermarked_pages': len(pages_to_watermark),
                'watermarked_page_numbers': [p + 1 for p in pages_to_watermark]  # Convert to 1-indexed
            }
            
            # Add type-specific details
            if watermark_type == 'text':
                summary.update({
                    'watermark_text': watermark_text,
                    'font': font,
                    'font_size': font_size,
                    'font_color': font_color
                })
            elif watermark_type == 'image':
                summary['watermark_image'] = Path(watermark_image).name
            elif watermark_type == 'pdf':
                summary['watermark_pdf'] = Path(watermark_pdf).name
            
            doc.close()
            return output_path, summary
        except Exception as e:
            logger.error(f"Error adding watermark to PDF {file_path}: {e}")
            raise PDFProcessingError(f"Failed to add watermark: {e}")
    
    @staticmethod
    def compress_pdf(file_path: Union[str, Path], compression_level: str = 'medium',
                    image_quality: int = None, image_dpi: int = None,
                    grayscale: bool = False, remove_annotations: bool = False,
                    remove_bookmarks: bool = False, remove_metadata: bool = False,
                    flatten_forms: bool = False) -> Tuple[str, Dict[str, Any]]:
        """Compress a PDF file.
        
        Args:
            file_path: Path to the PDF file
            compression_level: Compression level ('low', 'medium', 'high', 'extreme')
            image_quality: Image quality (0-100)
            image_dpi: Image DPI
            grayscale: Convert images to grayscale
            remove_annotations: Remove annotations
            remove_bookmarks: Remove bookmarks
            remove_metadata: Remove metadata
            flatten_forms: Flatten form fields
            
        Returns:
            Tuple[str, Dict]: Path to compressed PDF and compression summary
        """
        try:
            # Get compression settings based on level
            compression_settings = COMPRESSION_LEVELS.get(compression_level, COMPRESSION_LEVELS['medium'])
            
            # Override with custom settings if provided
            if image_quality is not None:
                compression_settings['image_quality'] = image_quality
            if image_dpi is not None:
                compression_settings['image_dpi'] = image_dpi
            
            # Open the PDF
            doc = fitz.open(file_path)
            
            # Get original file size
            original_size = os.path.getsize(file_path)
            
            # Apply compression settings
            for page_idx in range(len(doc)):
                page = doc[page_idx]
                
                # Process images on the page
                img_list = page.get_images(full=True)
                for img_idx, img_info in enumerate(img_list):
                    xref = img_info[0]
                    base_image = doc.extract_image(xref)
                    
                    if base_image:
                        # Process image (in a real implementation, this would recompress the image)
                        # For simulation, we'll just log the action
                        logger.info(f"Would compress image {img_idx} on page {page_idx+1} with quality {compression_settings['image_quality']} and DPI {compression_settings['image_dpi']}")
                
                # Remove annotations if requested
                if remove_annotations:
                    for annot in page.annots():
                        page.delete_annot(annot)
            
            # Remove bookmarks if requested
            if remove_bookmarks:
                doc.set_toc([])
            
            # Remove metadata if requested
            if remove_metadata:
                doc.set_metadata({})
            
            # Flatten form fields if requested
            if flatten_forms:
                # In a real implementation, this would flatten form fields
                # For simulation, we'll just log the action
                logger.info(f"Would flatten form fields in {file_path}")
            
            # Save compressed PDF
            output_path = f"{Path(file_path).stem}_compressed.pdf"
            doc.save(output_path, garbage=4, deflate=True, clean=True)
            doc.close()
            
            # Get compressed file size
            compressed_size = os.path.getsize(output_path)
            reduction_percentage = ((original_size - compressed_size) / original_size) * 100 if original_size > 0 else 0
            
            # Prepare summary
            summary = {
                'original_file': Path(file_path).name,
                'compressed_file': Path(output_path).name,
                'original_size': original_size,
                'compressed_size': compressed_size,
                'reduction_percentage': round(reduction_percentage, 2),
                'compression_level': compression_level,
                'settings': {
                    'image_quality': compression_settings['image_quality'],
                    'image_dpi': compression_settings['image_dpi'],
                    'grayscale': grayscale,
                    'remove_annotations': remove_annotations,
                    'remove_bookmarks': remove_bookmarks,
                    'remove_metadata': remove_metadata,
                    'flatten_forms': flatten_forms
                },
                'original_size_formatted': PDFUtility.format_file_size(original_size),
                'compressed_size_formatted': PDFUtility.format_file_size(compressed_size)
            }
            
            return output_path, summary
        except Exception as e:
            logger.error(f"Error compressing PDF {file_path}: {e}")
            raise PDFProcessingError(f"Failed to compress PDF: {e}")
    
    @staticmethod
    def format_file_size(size_bytes: int) -> str:
        """Format file size in human-readable format.
        
        Args:
            size_bytes: Size in bytes
            
        Returns:
            str: Formatted file size
        """
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0 or unit == 'GB':
                break
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} {unit}"
    
    @staticmethod
    def secure_pdf(file_path: Union[str, Path], user_password: str = None,
                  owner_password: str = None, encryption_level: int = DEFAULT_ENCRYPTION_LEVEL,
                  can_print: bool = True, can_modify: bool = True,
                  can_copy: bool = True, can_annotate: bool = True,
                  can_fill_forms: bool = True, can_extract: bool = True,
                  can_assemble: bool = True, can_print_high_quality: bool = True) -> Tuple[str, Dict[str, Any]]:
        """Secure a PDF with passwords and permissions.
        
        Args:
            file_path: Path to the PDF file
            user_password: Password required to open the document
            owner_password: Password required to change permissions
            encryption_level: Encryption level in bits (40, 128, or 256)
            can_print: Allow printing
            can_modify: Allow content modification
            can_copy: Allow content copying
            can_annotate: Allow annotations
            can_fill_forms: Allow form filling
            can_extract: Allow content extraction
            can_assemble: Allow document assembly
            can_print_high_quality: Allow high-quality printing
            
        Returns:
            Tuple[str, Dict]: Path to secured PDF and security summary
        """
        try:
            # Validate encryption level
            if encryption_level not in ENCRYPTION_LEVELS:
                raise ValueError(f"Invalid encryption level. Must be one of {ENCRYPTION_LEVELS}")
            
            # Validate passwords
            if user_password and len(user_password) < 4:
                raise ValueError("User password must be at least 4 characters long")
            if owner_password and len(owner_password) < 4:
                raise ValueError("Owner password must be at least 4 characters long")
            
            # Ensure either passwords are set or some permissions are restricted
            if not user_password and not owner_password and all([
                can_print, can_modify, can_copy, can_annotate,
                can_fill_forms, can_extract, can_assemble, can_print_high_quality
            ]):
                raise ValueError("Either passwords must be set or some permissions must be restricted")
            
            # Open the PDF
            doc = fitz.open(file_path)
            
            # Set permissions
            permissions = 0
            if can_print:
                permissions |= fitz.PDF_PERM_PRINT
            if can_modify:
                permissions |= fitz.PDF_PERM_MODIFY
            if can_copy:
                permissions |= fitz.PDF_PERM_COPY
            if can_annotate:
                permissions |= fitz.PDF_PERM_ANNOTATE
            if can_fill_forms:
                permissions |= fitz.PDF_PERM_FORM
            if can_extract:
                permissions |= fitz.PDF_PERM_EXTRACT
            if can_assemble:
                permissions |= fitz.PDF_PERM_ASSEMBLE
            if can_print_high_quality:
                permissions |= fitz.PDF_PERM_PRINT_HQ
            
            # Save secured PDF
            output_path = f"{Path(file_path).stem}_secured.pdf"
            doc.save(
                output_path,
                encryption=encryption_level,  # Encryption level
                user_pw=user_password,  # User password
                owner_pw=owner_password,  # Owner password
                permissions=permissions  # Permissions
            )
            doc.close()
            
            # Assess security strength
            security_strength = 'low'
            if encryption_level >= 128 and (user_password or owner_password) and not all([
                can_print, can_modify, can_copy, can_annotate,
                can_fill_forms, can_extract, can_assemble, can_print_high_quality
            ]):
                security_strength = 'medium'
            if encryption_level >= 256 and user_password and owner_password and not all([
                can_print, can_modify, can_copy, can_annotate,
                can_fill_forms, can_extract, can_assemble, can_print_high_quality
            ]):
                security_strength = 'high'
            
            # Prepare summary
            summary = {
                'original_file': Path(file_path).name,
                'secured_file': Path(output_path).name,
                'page_count': len(doc),
                'encryption_level': encryption_level,
                'has_user_password': bool(user_password),
                'has_owner_password': bool(owner_password),
                'permissions': {
                    'can_print': can_print,
                    'can_modify': can_modify,
                    'can_copy': can_copy,
                    'can_annotate': can_annotate,
                    'can_fill_forms': can_fill_forms,
                    'can_extract': can_extract,
                    'can_assemble': can_assemble,
                    'can_print_high_quality': can_print_high_quality
                },
                'security_strength': security_strength,
                'allowed_actions': [k for k, v in {
                    'printing': can_print,
                    'content modification': can_modify,
                    'content copying': can_copy,
                    'annotations': can_annotate,
                    'form filling': can_fill_forms,
                    'content extraction': can_extract,
                    'document assembly': can_assemble,
                    'high-quality printing': can_print_high_quality
                }.items() if v],
                'restricted_actions': [k for k, v in {
                    'printing': not can_print,
                    'content modification': not can_modify,
                    'content copying': not can_copy,
                    'annotations': not can_annotate,
                    'form filling': not can_fill_forms,
                    'content extraction': not can_extract,
                    'document assembly': not can_assemble,
                    'high-quality printing': not can_print_high_quality
                }.items() if v]
            }
            
            return output_path, summary
        except Exception as e:
            logger.error(f"Error securing PDF {file_path}: {e}")
            raise PDFProcessingError(f"Failed to secure PDF: {e}")
    
    @staticmethod
    def optimize_pdf(file_path: Union[str, Path], optimization_profile: str = 'balanced',
                    target_size_kb: int = None, custom_params: Dict[str, Any] = None) -> Tuple[str, Dict[str, Any]]:
        """Optimize a PDF for specific use cases.
        
        Args:
            file_path: Path to the PDF file
            optimization_profile: Optimization profile ('web', 'print', 'ebook', 'balanced', 'custom')
            target_size_kb: Target file size in KB (optional)
            custom_params: Custom optimization parameters (for 'custom' profile)
            
        Returns:
            Tuple[str, Dict]: Path to optimized PDF and optimization summary
        """
        try:
            # Get optimization settings based on profile
            if optimization_profile == 'custom' and custom_params:
                optimization_settings = custom_params
            else:
                optimization_settings = OPTIMIZATION_PROFILES.get(optimization_profile, OPTIMIZATION_PROFILES['balanced'])
            
            # Open the PDF
            doc = fitz.open(file_path)
            
            # Get original file size
            original_size = os.path.getsize(file_path)
            
            # Apply optimization settings
            for page_idx in range(len(doc)):
                page = doc[page_idx]
                
                # Process images on the page
                img_list = page.get_images(full=True)
                for img_idx, img_info in enumerate(img_list):
                    xref = img_info[0]
                    base_image = doc.extract_image(xref)
                    
                    if base_image:
                        # Process image (in a real implementation, this would optimize the image)
                        # For simulation, we'll just log the action
                        logger.info(f"Would optimize image {img_idx} on page {page_idx+1} with settings: {optimization_settings}")
            
            # Apply other optimizations based on settings
            if optimization_settings.get('remove_unused_objects', False):
                # In a real implementation, this would remove unused objects
                logger.info(f"Would remove unused objects from {file_path}")
            
            if optimization_settings.get('remove_metadata', False):
                doc.set_metadata({})
            
            # Save optimized PDF
            output_path = f"{Path(file_path).stem}_optimized.pdf"
            doc.save(
                output_path,
                garbage=4,  # Maximum garbage collection
                deflate=True,  # Compress streams
                clean=True,  # Clean content streams
                linear=optimization_settings.get('linearize', False)  # Linearize for web optimization
            )
            doc.close()
            
            # Get optimized file size
            optimized_size = os.path.getsize(output_path)
            reduction_percentage = ((original_size - optimized_size) / original_size) * 100 if original_size > 0 else 0
            
            # Prepare summary
            summary = {
                'original_file': Path(file_path).name,
                'optimized_file': Path(output_path).name,
                'original_size': original_size,
                'optimized_size': optimized_size,
                'reduction_percentage': round(reduction_percentage, 2),
                'optimization_profile': optimization_profile,
                'settings': optimization_settings,
                'original_size_formatted': PDFUtility.format_file_size(original_size),
                'optimized_size_formatted': PDFUtility.format_file_size(optimized_size)
            }
            
            # Add target size info if provided
            if target_size_kb:
                target_size = target_size_kb * 1024
                summary['target_size'] = target_size
                summary['target_size_formatted'] = PDFUtility.format_file_size(target_size)
                summary['target_achieved'] = optimized_size <= target_size
            
            return output_path, summary
        except Exception as e:
            logger.error(f"Error optimizing PDF {file_path}: {e}")
            raise PDFProcessingError(f"Failed to optimize PDF: {e}")