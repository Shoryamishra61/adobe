import os
import re
import json
import uuid
import tempfile
import difflib
import numpy as np
from pathlib import Path
from typing import List, Dict, Any, Optional, Union, Tuple
import logging

# Import PDF processing libraries
import fitz  # PyMuPDF
import pdfplumber

# Import from project
from .pdf_processing import PDFUtility, PDFProcessingError

# Get logger
logger = logging.getLogger(__name__)

class PDFComparisonError(Exception):
    """Exception raised for errors in PDF comparison."""
    pass

class PDFComparison:
    """Class for comparing PDF documents."""
    
    @staticmethod
    def compare_pdfs(file_paths: List[Union[str, Path]], comparison_level: str = 'content',
                    highlight_differences: bool = True, include_text_diff: bool = True,
                    include_visual_diff: bool = False, sensitivity: float = 0.8,
                    ignore_whitespace: bool = False, ignore_case: bool = False,
                    ignore_formatting: bool = False) -> Dict[str, Any]:
        """Compare multiple PDF documents.
        
        Args:
            file_paths: List of paths to PDF files to compare
            comparison_level: Level of comparison ('content', 'visual', 'both')
            highlight_differences: Whether to highlight differences in the output
            include_text_diff: Whether to include text differences in the output
            include_visual_diff: Whether to include visual differences in the output
            sensitivity: Sensitivity threshold for differences (0.0-1.0)
            ignore_whitespace: Whether to ignore whitespace differences
            ignore_case: Whether to ignore case differences
            ignore_formatting: Whether to ignore formatting differences
            
        Returns:
            Dict: Comparison results
        """
        try:
            # Validate inputs
            if len(file_paths) < 2:
                raise ValueError("At least two PDF files are required for comparison")
            
            # Validate all files are PDFs
            for file_path in file_paths:
                if not PDFUtility.validate_pdf(file_path):
                    raise ValueError(f"Invalid PDF file: {file_path}")
            
            # Extract metadata for all files
            metadata_list = [PDFUtility.extract_metadata(file_path) for file_path in file_paths]
            
            # Initialize results
            results = {
                'files': [Path(file_path).name for file_path in file_paths],
                'metadata': metadata_list,
                'comparison_level': comparison_level,
                'settings': {
                    'highlight_differences': highlight_differences,
                    'include_text_diff': include_text_diff,
                    'include_visual_diff': include_visual_diff,
                    'sensitivity': sensitivity,
                    'ignore_whitespace': ignore_whitespace,
                    'ignore_case': ignore_case,
                    'ignore_formatting': ignore_formatting
                },
                'differences': {},
                'similarity_scores': {},
                'summary': {}
            }
            
            # Perform content comparison if requested
            if comparison_level in ['content', 'both']:
                content_results = PDFComparison.compare_content(
                    file_paths, 
                    sensitivity=sensitivity,
                    ignore_whitespace=ignore_whitespace,
                    ignore_case=ignore_case,
                    ignore_formatting=ignore_formatting,
                    include_text_diff=include_text_diff
                )
                results['differences']['content'] = content_results['differences']
                results['similarity_scores']['content'] = content_results['similarity_scores']
            
            # Perform visual comparison if requested
            if comparison_level in ['visual', 'both']:
                visual_results = PDFComparison.compare_visual(
                    file_paths,
                    sensitivity=sensitivity,
                    include_visual_diff=include_visual_diff
                )
                results['differences']['visual'] = visual_results['differences']
                results['similarity_scores']['visual'] = visual_results['similarity_scores']
            
            # Generate summary
            results['summary'] = PDFComparison.generate_comparison_summary(results)
            
            return results
        except Exception as e:
            logger.error(f"Error comparing PDFs: {e}")
            raise PDFComparisonError(f"Failed to compare PDFs: {e}")
    
    @staticmethod
    def compare_content(file_paths: List[Union[str, Path]], sensitivity: float = 0.8,
                      ignore_whitespace: bool = False, ignore_case: bool = False,
                      ignore_formatting: bool = False, include_text_diff: bool = True) -> Dict[str, Any]:
        """Compare the content of multiple PDF documents.
        
        Args:
            file_paths: List of paths to PDF files to compare
            sensitivity: Sensitivity threshold for differences (0.0-1.0)
            ignore_whitespace: Whether to ignore whitespace differences
            ignore_case: Whether to ignore case differences
            ignore_formatting: Whether to ignore formatting differences
            include_text_diff: Whether to include text differences in the output
            
        Returns:
            Dict: Content comparison results
        """
        try:
            # Extract text from all PDFs
            text_contents = []
            for file_path in file_paths:
                doc = fitz.open(file_path)
                text = ""
                for page in doc:
                    page_text = page.get_text("text")
                    text += page_text
                doc.close()
                
                # Apply text normalization based on settings
                if ignore_whitespace:
                    text = re.sub(r'\s+', ' ', text)
                if ignore_case:
                    text = text.lower()
                if ignore_formatting:
                    # Remove common formatting characters
                    text = re.sub(r'[\n\r\t\f\v]', ' ', text)
                    text = re.sub(r'\s+', ' ', text)
                
                text_contents.append(text)
            
            # Initialize results
            results = {
                'differences': {},
                'similarity_scores': {}
            }
            
            # Compare each pair of documents
            num_files = len(file_paths)
            for i in range(num_files):
                for j in range(i+1, num_files):
                    file1 = Path(file_paths[i]).name
                    file2 = Path(file_paths[j]).name
                    pair_key = f"{file1}_vs_{file2}"
                    
                    # Calculate similarity score
                    similarity = PDFComparison.calculate_text_similarity(text_contents[i], text_contents[j])
                    results['similarity_scores'][pair_key] = round(similarity, 4)
                    
                    # Determine if the difference is significant based on sensitivity
                    is_different = similarity < sensitivity
                    
                    # Generate text diff if requested and if there are differences
                    if include_text_diff and is_different:
                        diff = PDFComparison.generate_text_diff(
                            text_contents[i], text_contents[j],
                            context_lines=3  # Number of context lines around differences
                        )
                        
                        # Count differences
                        diff_count = sum(1 for line in diff if line.startswith('+ ') or line.startswith('- '))
                        
                        results['differences'][pair_key] = {
                            'is_different': is_different,
                            'similarity': round(similarity, 4),
                            'diff_count': diff_count,
                            'diff': diff if diff else ["No significant differences found."]
                        }
                    else:
                        results['differences'][pair_key] = {
                            'is_different': is_different,
                            'similarity': round(similarity, 4),
                            'diff_count': 0,
                            'diff': ["Text diff not included in results."]
                        }
            
            return results
        except Exception as e:
            logger.error(f"Error comparing PDF content: {e}")
            raise PDFComparisonError(f"Failed to compare PDF content: {e}")
    
    @staticmethod
    def compare_visual(file_paths: List[Union[str, Path]], sensitivity: float = 0.8,
                     include_visual_diff: bool = False) -> Dict[str, Any]:
        """Compare the visual appearance of multiple PDF documents.
        
        Args:
            file_paths: List of paths to PDF files to compare
            sensitivity: Sensitivity threshold for differences (0.0-1.0)
            include_visual_diff: Whether to include visual differences in the output
            
        Returns:
            Dict: Visual comparison results
        """
        try:
            # Initialize results
            results = {
                'differences': {},
                'similarity_scores': {}
            }
            
            # Compare each pair of documents
            num_files = len(file_paths)
            for i in range(num_files):
                for j in range(i+1, num_files):
                    file1 = Path(file_paths[i]).name
                    file2 = Path(file_paths[j]).name
                    pair_key = f"{file1}_vs_{file2}"
                    
                    # Simulate visual comparison (in a real implementation, this would use image comparison)
                    # For this simulation, we'll generate random similarity scores and differences
                    
                    # Open both documents
                    doc1 = fitz.open(file_paths[i])
                    doc2 = fitz.open(file_paths[j])
                    
                    # Check if documents have the same number of pages
                    same_page_count = len(doc1) == len(doc2)
                    
                    # Compare page by page if they have the same number of pages
                    page_similarities = []
                    page_differences = []
                    
                    if same_page_count:
                        for page_idx in range(len(doc1)):
                            # In a real implementation, this would compare page images
                            # For simulation, we'll use a simplified approach
                            
                            # Get page dimensions
                            page1 = doc1[page_idx]
                            page2 = doc2[page_idx]
                            
                            # Check if pages have the same dimensions
                            same_dimensions = page1.rect.width == page2.rect.width and page1.rect.height == page2.rect.height
                            
                            # Simulate visual similarity (in reality, this would be based on image comparison)
                            # For simulation, we'll use a combination of factors
                            if same_dimensions:
                                # Get text similarity as a proxy for visual similarity
                                text1 = page1.get_text("text")
                                text2 = page2.get_text("text")
                                text_sim = PDFComparison.calculate_text_similarity(text1, text2)
                                
                                # Count images on each page
                                img_count1 = len(page1.get_images())
                                img_count2 = len(page2.get_images())
                                img_sim = 1.0 if img_count1 == img_count2 else 0.5
                                
                                # Combine factors for overall page similarity
                                page_sim = (text_sim * 0.7) + (img_sim * 0.3)  # Weighted average
                            else:
                                # Different dimensions indicate different layouts
                                page_sim = 0.3  # Low similarity for different dimensions
                            
                            page_similarities.append(page_sim)
                            
                            # Record page differences if below threshold
                            if page_sim < sensitivity:
                                page_differences.append({
                                    'page_number': page_idx + 1,
                                    'similarity': round(page_sim, 4),
                                    'same_dimensions': same_dimensions,
                                    'width1': page1.rect.width,
                                    'height1': page1.rect.height,
                                    'width2': page2.rect.width,
                                    'height2': page2.rect.height
                                })
                    
                    # Calculate overall visual similarity
                    if page_similarities:
                        overall_similarity = sum(page_similarities) / len(page_similarities)
                    else:
                        overall_similarity = 0.0
                    
                    # Determine if the difference is significant based on sensitivity
                    is_different = overall_similarity < sensitivity
                    
                    # Store results
                    results['similarity_scores'][pair_key] = round(overall_similarity, 4)
                    
                    results['differences'][pair_key] = {
                        'is_different': is_different,
                        'similarity': round(overall_similarity, 4),
                        'same_page_count': same_page_count,
                        'page_count1': len(doc1),
                        'page_count2': len(doc2),
                        'different_pages': page_differences,
                        'diff_count': len(page_differences)
                    }
                    
                    # Include visual diff if requested
                    if include_visual_diff and is_different:
                        # In a real implementation, this would generate visual diff images
                        # For simulation, we'll just note that visual diff would be included
                        results['differences'][pair_key]['visual_diff'] = [
                            f"Visual diff would be generated for pages: {', '.join([str(d['page_number']) for d in page_differences])}"
                        ]
                    
                    # Close documents
                    doc1.close()
                    doc2.close()
            
            return results
        except Exception as e:
            logger.error(f"Error comparing PDF visually: {e}")
            raise PDFComparisonError(f"Failed to compare PDF visually: {e}")
    
    @staticmethod
    def calculate_text_similarity(text1: str, text2: str) -> float:
        """Calculate similarity between two text strings.
        
        Args:
            text1: First text string
            text2: Second text string
            
        Returns:
            float: Similarity score (0.0-1.0)
        """
        # Use SequenceMatcher for similarity calculation
        matcher = difflib.SequenceMatcher(None, text1, text2)
        return matcher.ratio()
    
    @staticmethod
    def generate_text_diff(text1: str, text2: str, context_lines: int = 3) -> List[str]:
        """Generate a human-readable diff between two text strings.
        
        Args:
            text1: First text string
            text2: Second text string
            context_lines: Number of context lines around differences
            
        Returns:
            List[str]: List of diff lines
        """
        # Split texts into lines
        lines1 = text1.splitlines()
        lines2 = text2.splitlines()
        
        # Generate unified diff
        diff = difflib.unified_diff(
            lines1, lines2,
            fromfile='Document 1',
            tofile='Document 2',
            n=context_lines,
            lineterm=''
        )
        
        # Convert diff iterator to list
        diff_list = list(diff)
        
        # If diff is too large, truncate it
        max_diff_lines = 1000
        if len(diff_list) > max_diff_lines:
            diff_list = diff_list[:max_diff_lines]
            diff_list.append(f"... [Diff truncated, {len(diff_list) - max_diff_lines} more lines]")
        
        return diff_list
    
    @staticmethod
    def generate_comparison_summary(results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a summary of comparison results.
        
        Args:
            results: Comparison results
            
        Returns:
            Dict: Summary of comparison results
        """
        summary = {
            'file_count': len(results['files']),
            'files': results['files'],
            'comparison_level': results['comparison_level'],
            'overall_similarity': {},
            'different_file_pairs': [],
            'identical_file_pairs': [],
            'most_similar_pair': None,
            'least_similar_pair': None
        }
        
        # Process content similarity if available
        if 'content' in results.get('similarity_scores', {}):
            content_scores = results['similarity_scores']['content']
            if content_scores:
                # Calculate average content similarity
                avg_content_similarity = sum(content_scores.values()) / len(content_scores)
                summary['overall_similarity']['content'] = round(avg_content_similarity, 4)
                
                # Find most and least similar pairs
                most_similar = max(content_scores.items(), key=lambda x: x[1])
                least_similar = min(content_scores.items(), key=lambda x: x[1])
                
                summary['most_similar_pair'] = {
                    'files': most_similar[0],
                    'similarity': most_similar[1],
                    'type': 'content'
                }
                
                summary['least_similar_pair'] = {
                    'files': least_similar[0],
                    'similarity': least_similar[1],
                    'type': 'content'
                }
        
        # Process visual similarity if available
        if 'visual' in results.get('similarity_scores', {}):
            visual_scores = results['similarity_scores']['visual']
            if visual_scores:
                # Calculate average visual similarity
                avg_visual_similarity = sum(visual_scores.values()) / len(visual_scores)
                summary['overall_similarity']['visual'] = round(avg_visual_similarity, 4)
                
                # Update most and least similar pairs if visual similarity is more extreme
                most_similar = max(visual_scores.items(), key=lambda x: x[1])
                least_similar = min(visual_scores.items(), key=lambda x: x[1])
                
                if 'most_similar_pair' not in summary or most_similar[1] > summary['most_similar_pair']['similarity']:
                    summary['most_similar_pair'] = {
                        'files': most_similar[0],
                        'similarity': most_similar[1],
                        'type': 'visual'
                    }
                
                if 'least_similar_pair' not in summary or least_similar[1] < summary['least_similar_pair']['similarity']:
                    summary['least_similar_pair'] = {
                        'files': least_similar[0],
                        'similarity': least_similar[1],
                        'type': 'visual'
                    }
        
        # Calculate overall similarity across all comparison types
        if summary['overall_similarity']:
            summary['overall_similarity']['combined'] = round(
                sum(summary['overall_similarity'].values()) / len(summary['overall_similarity']),
                4
            )
        
        # Identify different and identical file pairs
        sensitivity = results['settings']['sensitivity']
        
        # Check content differences if available
        if 'content' in results.get('differences', {}):
            for pair, diff in results['differences']['content'].items():
                if diff['is_different']:
                    if pair not in summary['different_file_pairs']:
                        summary['different_file_pairs'].append(pair)
                elif pair not in summary['identical_file_pairs'] and pair not in summary['different_file_pairs']:
                    summary['identical_file_pairs'].append(pair)
        
        # Check visual differences if available
        if 'visual' in results.get('differences', {}):
            for pair, diff in results['differences']['visual'].items():
                if diff['is_different']:
                    if pair not in summary['different_file_pairs']:
                        summary['different_file_pairs'].append(pair)
                elif pair not in summary['identical_file_pairs'] and pair not in summary['different_file_pairs']:
                    summary['identical_file_pairs'].append(pair)
        
        # Add counts
        summary['different_pair_count'] = len(summary['different_file_pairs'])
        summary['identical_pair_count'] = len(summary['identical_file_pairs'])
        
        # Generate overall assessment
        if summary['different_pair_count'] == 0:
            summary['assessment'] = "All documents are substantially similar."
        elif summary['identical_pair_count'] == 0:
            summary['assessment'] = "All document pairs have significant differences."
        else:
            summary['assessment'] = f"{summary['identical_pair_count']} document pairs are similar, while {summary['different_pair_count']} pairs have significant differences."
        
        return summary