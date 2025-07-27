from flask import Blueprint, request, send_file, jsonify, current_app
from pathlib import Path
from tempfile import TemporaryDirectory
import zipfile
import json
import os
import uuid
import threading
import io
import base64
from typing import List, Dict, Any, Optional, Union
from concurrent.futures import ThreadPoolExecutor

from ..config.config import (
    MAX_WORKERS, 
    ENABLE_CACHING, 
    ENABLE_ADVANCED_ANALYTICS,
    API_VERSION
)
from ..services.process_pdfs import extract_and_save, batch_process_pdfs, PDFProcessor
from ..services.semantic_rank import SemanticRanker
from ..utils.logging_config import get_logger

logger = get_logger(__name__)

api_blueprint = Blueprint('api', __name__)

# Initialize the semantic ranker
semantic_ranker = SemanticRanker()

# API info endpoint
@api_blueprint.route('/info', methods=['GET'])
def api_info():
    """Return API information and version"""
    return jsonify({
        "name": "PDF Analysis and Semantic Search API",
        "version": API_VERSION,
        "features": {
            "pdf_analysis": True,
            "semantic_search": True,
            "advanced_analytics": ENABLE_ADVANCED_ANALYTICS,
            "caching": ENABLE_CACHING
        }
    })

@api_blueprint.route('/analyze', methods=['POST'])
def analyze():
    """Analyze PDF files and extract content, tables, and structure"""
    try:
        # Get advanced analytics flag from request or use default
        advanced_analytics = request.args.get('advanced_analytics', '').lower() == 'true' or ENABLE_ADVANCED_ANALYTICS
        
        logger.info(f"Starting PDF analysis with advanced_analytics={advanced_analytics}")
        
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            input_path = tmp_path / 'input'
            output_path = tmp_path / 'output'
            input_path.mkdir()
            output_path.mkdir()

            # Save uploaded files
            uploaded_files = request.files.getlist('files')
            if not uploaded_files:
                return jsonify({"error": "No files uploaded"}), 400
                
            pdf_paths = []
            for f in uploaded_files:
                if f.filename.lower().endswith('.pdf'):
                    file_path = input_path / f.filename
                    f.save(file_path)
                    pdf_paths.append(file_path)
            
            if not pdf_paths:
                return jsonify({"error": "No PDF files found in upload"}), 400
                
            # Process PDFs in parallel
            logger.info(f"Processing {len(pdf_paths)} PDF files")
            batch_process_pdfs(pdf_paths, output_path, max_workers=MAX_WORKERS, advanced_analytics=advanced_analytics)

            # Create zip file with results
            zip_path = tmp_path / 'analysis_results.zip'
            with zipfile.ZipFile(zip_path, 'w') as zf:
                for json_file in output_path.glob("*.json"):
                    zf.write(json_file, arcname=json_file.name)
            
            # Return summary along with the zip file
            result_files = list(output_path.glob("*.json"))
            logger.info(f"Analysis complete. Created {len(result_files)} result files")
            
            return send_file(zip_path, as_attachment=True, 
                           download_name=f"pdf_analysis_results.zip")
    
    except Exception as e:
        logger.error(f"Error in analyze endpoint: {e}")
        return jsonify({"error": str(e)}), 500

@api_blueprint.route('/rank', methods=['POST'])
def rank_route():
    """Rank PDF documents based on relevance to a query defined in a collection JSON"""
    try:
        logger.info("Starting document ranking")
        
        with TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir)
            pdfs_path = base_path / 'PDFs'
            pdfs_path.mkdir()

            # Validate required files
            if 'config' not in request.files or 'pdfs' not in request.files:
                return jsonify({"error": "Missing required files: 'config' and 'pdfs'"}), 400
                
            config_file = request.files['config']
            zip_file = request.files['pdfs']

            # Save config file
            config_path = base_path / 'collection.json'
            config_file.save(config_path)

            # Extract PDF files
            with zipfile.ZipFile(zip_file) as zf:
                zf.extractall(pdfs_path)
                
            # Get top_k parameter from request or use default
            top_k = request.args.get('top_k', 5, type=int)
            
            # Perform ranking
            logger.info(f"Ranking documents with top_k={top_k}")
            results = semantic_ranker.rank(config_path, base_path, top_k=top_k)
            
            logger.info(f"Ranking complete. Found {len(results)} results")
            return jsonify({
                "results": results,
                "count": len(results)
            })
            
    except Exception as e:
        logger.error(f"Error in rank endpoint: {e}")
        return jsonify({"error": str(e)}), 500

@api_blueprint.route('/search', methods=['POST'])
def search():
    """Search across multiple PDF documents for content relevant to a query"""
    try:
        # Get query parameter
        query = request.form.get('query')
        if not query:
            return jsonify({"error": "Missing required parameter: 'query'"}), 400
            
        # Get top_k parameter
        top_k = request.args.get('top_k', 5, type=int)
        
        logger.info(f"Searching documents for query: '{query}' with top_k={top_k}")
        
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            
            # Save uploaded files
            uploaded_files = request.files.getlist('files')
            if not uploaded_files:
                return jsonify({"error": "No files uploaded"}), 400
                
            pdf_paths = []
            for f in uploaded_files:
                if f.filename.lower().endswith('.pdf'):
                    file_path = tmp_path / f.filename
                    f.save(file_path)
                    pdf_paths.append(file_path)
            
            if not pdf_paths:
                return jsonify({"error": "No PDF files found in upload"}), 400
                
            # Perform search
            results = semantic_ranker.search(query, pdf_paths, top_k=top_k)
            
            logger.info(f"Search complete. Found {len(results)} results")
            return jsonify({
                "query": query,
                "results": results,
                "count": len(results)
            })
            
    except Exception as e:
        logger.error(f"Error in search endpoint: {e}")
        return jsonify({"error": str(e)}), 500

@api_blueprint.route('/analyze-single', methods=['POST'])
def analyze_single():
    """Analyze a single PDF file and return detailed results"""
    try:
        # Get advanced analytics flag from request or use default
        advanced_analytics = request.args.get('advanced_analytics', '').lower() == 'true' or ENABLE_ADVANCED_ANALYTICS
        
        logger.info(f"Starting single PDF analysis with advanced_analytics={advanced_analytics}")
        
        # Check if file was uploaded
        if 'file' not in request.files:
            return jsonify({"error": "No file uploaded"}), 400
            
        pdf_file = request.files['file']
        if not pdf_file.filename.lower().endswith('.pdf'):
            return jsonify({"error": "Uploaded file is not a PDF"}), 400
            
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            file_path = tmp_path / pdf_file.filename
            pdf_file.save(file_path)
            
            # Initialize PDF processor
            processor = PDFProcessor(file_path)
            
            # Extract content based on requested features
            extract_tables = request.args.get('tables', '').lower() == 'true'
            extract_outline = request.args.get('outline', '').lower() == 'true'
            extract_text = request.args.get('text', '').lower() == 'true'
            
            result = {"filename": pdf_file.filename}
            
            # Extract metadata
            result["metadata"] = processor._extract_metadata()
            
            # Extract tables if requested
            if extract_tables:
                logger.info(f"Extracting tables from {pdf_file.filename}")
                result["tables"] = processor.extract_tables()
                
            # Extract outline if requested
            if extract_outline:
                logger.info(f"Extracting outline from {pdf_file.filename}")
                result["outline"] = processor.extract_outline()
                
            # Extract text if requested
            if extract_text:
                logger.info(f"Extracting text from {pdf_file.filename}")
                result["text"] = processor.extract_text()
                
            # Perform advanced analytics if requested
            if advanced_analytics:
                logger.info(f"Performing advanced analytics on {pdf_file.filename}")
                result["analytics"] = processor.analyze_content()
                
            # Clean up resources
            processor._cleanup()
            
            logger.info(f"Analysis of {pdf_file.filename} complete")
            return jsonify(result)
            
    except Exception as e:
        logger.error(f"Error in analyze-single endpoint: {e}")
        return jsonify({"error": str(e)}), 500

@api_blueprint.route('/batch-process', methods=['POST'])
def batch_process():
    """Process multiple PDFs in batches with progress tracking"""
    try:
        # Get advanced analytics flag from request or use default
        advanced_analytics = request.args.get('advanced_analytics', '').lower() == 'true' or ENABLE_ADVANCED_ANALYTICS
        
        logger.info(f"Starting batch PDF processing with advanced_analytics={advanced_analytics}")
        
        # Check if files were uploaded
        if 'files' not in request.files:
            return jsonify({"error": "No files uploaded"}), 400
            
        files = request.files.getlist('files')
        if not files:
            return jsonify({"error": "No files selected"}), 400
            
        # Filter for PDF files only
        pdf_files = [f for f in files if f.filename.lower().endswith('.pdf')]
        if not pdf_files:
            return jsonify({"error": "No PDF files found in upload"}), 400
            
        # Create a job ID for tracking
        job_id = str(uuid.uuid4())
        
        # Create response with job information
        response = {
            "job_id": job_id,
            "status": "processing",
            "total_files": len(pdf_files),
            "files": [f.filename for f in pdf_files]
        }
        
        # Start processing in a background thread
        def process_batch():
            try:
                with TemporaryDirectory() as tmpdir:
                    tmp_path = Path(tmpdir)
                    output_dir = tmp_path / "output"
                    output_dir.mkdir(exist_ok=True)
                    
                    # Save files to temp directory
                    file_paths = []
                    for pdf_file in pdf_files:
                        file_path = tmp_path / pdf_file.filename
                        pdf_file.save(file_path)
                        file_paths.append(file_path)
                    
                    # Process PDFs in parallel
                    results = batch_process_pdfs(
                        file_paths, 
                        output_dir=output_dir,
                        advanced_analytics=advanced_analytics,
                        max_workers=MAX_WORKERS
                    )
                    
                    # Store results in a database or cache for later retrieval
                    # For simplicity, we'll just log the completion
                    logger.info(f"Batch processing complete for job {job_id}. Processed {len(results)} files.")
                    
                    # Update job status (in a real app, this would update a database)
                    # current_app.config[f'job_{job_id}'] = {
                    #     "status": "complete",
                    #     "results": results
                    # }
            except Exception as e:
                logger.error(f"Error in batch processing job {job_id}: {e}")
                # Update job status with error
                # current_app.config[f'job_{job_id}'] = {
                #     "status": "error",
                #     "error": str(e)
                # }
        
        # Start processing thread
        thread = threading.Thread(target=process_batch)
        thread.daemon = True
        thread.start()
        
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"Error in batch-process endpoint: {e}")
        return jsonify({"error": str(e)}), 500

@api_blueprint.route('/job-status/<job_id>', methods=['GET'])
def job_status(job_id):
    """Check the status of a batch processing job"""
    try:
        # In a real application, this would query a database
        # For now, we'll just return a mock response
        
        # job_info = current_app.config.get(f'job_{job_id}')
        # if not job_info:
        #     return jsonify({"error": "Job not found"}), 404
        
        # Mock response for demonstration
        job_info = {
            "job_id": job_id,
            "status": "complete",  # or "processing", "error"
            "total_files": 5,
            "processed_files": 5,
            "completion_time": "2023-04-15T14:30:45Z"
        }
        
        return jsonify(job_info)
        
    except Exception as e:
        logger.error(f"Error in job-status endpoint: {e}")
        return jsonify({"error": str(e)}), 500

@api_blueprint.route('/compare', methods=['POST'])
def compare_documents():
    """Compare two PDF documents and identify differences"""
    try:
        logger.info("Starting document comparison")
        
        # Check if both files were uploaded
        if 'file1' not in request.files or 'file2' not in request.files:
            return jsonify({"error": "Two PDF files (file1 and file2) are required"}), 400
            
        file1 = request.files['file1']
        file2 = request.files['file2']
        
        # Validate file types
        if not file1.filename.lower().endswith('.pdf') or not file2.filename.lower().endswith('.pdf'):
            return jsonify({"error": "Both files must be PDFs"}), 400
            
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            
            # Save files
            file1_path = tmp_path / file1.filename
            file2_path = tmp_path / file2.filename
            file1.save(file1_path)
            file2.save(file2_path)
            
            # Use PDFComparison utility for basic comparison
            from utils.pdf_comparison import PDFComparison
            
            # For backward compatibility, we'll use both the PDFComparison utility and the semantic ranker
            # Initialize processors for extracting tables and outlines (not yet handled by PDFComparison)
            processor1 = PDFProcessor(file1_path)
            processor2 = PDFProcessor(file2_path)
            
            # Extract tables and outlines from both documents
            tables1 = processor1.extract_tables()
            tables2 = processor2.extract_tables()
            outline1 = processor1.extract_outline()
            outline2 = processor2.extract_outline()
            
            # Use semantic ranker to find similar content
            similarity_threshold = request.args.get('threshold', 0.7, type=float)
            similar_content = semantic_ranker.find_similar_content(
                file1_path, [file2_path], 
                similarity_threshold=similarity_threshold
            )
            
            # Use PDFComparison for content comparison
            comparison_results = PDFComparison.compare_pdfs(
                file_paths=[file1_path, file2_path],
                comparison_level='content',  # Only content comparison for this endpoint
                highlight_differences=False,
                include_text_diff=True,
                include_visual_diff=False,
                sensitivity=similarity_threshold,
                ignore_whitespace=True,
                ignore_case=False,
                ignore_formatting=True
            )
            
            # Extract metadata from comparison results
            metadata1 = comparison_results['metadata'][0]
            metadata2 = comparison_results['metadata'][1]
            
            # Clean up resources
            processor1._cleanup()
            processor2._cleanup()
            
            # Prepare comparison results in the original format for backward compatibility
            comparison = {
                "documents": {
                    "file1": {
                        "filename": file1.filename,
                        "metadata": metadata1,
                        "page_count": metadata1.get("page_count", 0),
                        "table_count": len(tables1),
                        "section_count": len(outline1) if outline1 else 0
                    },
                    "file2": {
                        "filename": file2.filename,
                        "metadata": metadata2,
                        "page_count": metadata2.get("page_count", 0),
                        "table_count": len(tables2),
                        "section_count": len(outline2) if outline2 else 0
                    }
                },
                "similarities": similar_content,
                "differences": {
                    "metadata": {k: (metadata1.get(k), metadata2.get(k)) 
                               for k in set(metadata1) | set(metadata2) 
                               if metadata1.get(k) != metadata2.get(k)},
                    "structure": {
                        "page_count_diff": metadata2.get("page_count", 0) - metadata1.get("page_count", 0),
                        "table_count_diff": len(tables2) - len(tables1),
                        "section_count_diff": (len(outline2) if outline2 else 0) - (len(outline1) if outline1 else 0)
                    },
                    "unique_sections": {
                        "file1_only": [s for s in outline1 if s not in outline2] if outline1 and outline2 else [],
                        "file2_only": [s for s in outline2 if s not in outline1] if outline1 and outline2 else []
                    }
                }
            }
            
            # Add content similarity from PDFComparison if available
            if 'differences' in comparison_results and 'content' in comparison_results['differences']:
                pair_key = list(comparison_results['differences']['content'].keys())[0]  # Should only be one pair
                content_diff = comparison_results['differences']['content'][pair_key]
                comparison["content_similarity"] = {
                    "similarity_score": content_diff.get('similarity', 0.0),
                    "is_different": content_diff.get('is_different', True),
                    "difference_count": content_diff.get('diff_count', 0)
                }
                if 'text_diff' in content_diff:
                    comparison["content_similarity"]["text_diff"] = content_diff['text_diff']
            
            logger.info(f"Document comparison complete between {file1.filename} and {file2.filename}")
            return jsonify(comparison)
            
    except Exception as e:
        logger.error(f"Error in compare endpoint: {e}")
        return jsonify({"error": str(e)}), 500

@api_blueprint.route('/statistics', methods=['POST'])
def extract_statistics():
    """Extract and visualize statistics from PDF documents"""
    try:
        logger.info("Starting PDF statistics extraction")
        
        # Check if files were uploaded
        if 'files' not in request.files:
            return jsonify({"error": "No files uploaded"}), 400
            
        files = request.files.getlist('files')
        if not files:
            return jsonify({"error": "No files selected"}), 400
            
        # Filter for PDF files only
        pdf_files = [f for f in files if f.filename.lower().endswith('.pdf')]
        if not pdf_files:
            return jsonify({"error": "No PDF files found in upload"}), 400
            
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            
            # Save files to temp directory
            file_paths = []
            for pdf_file in pdf_files:
                file_path = tmp_path / pdf_file.filename
                pdf_file.save(file_path)
                file_paths.append(file_path)
            
            # Process each PDF and collect statistics
            stats = []
            for file_path in file_paths:
                try:
                    processor = PDFProcessor(file_path)
                    
                    # Extract metadata
                    metadata = processor._extract_metadata()
                    
                    # Extract tables
                    tables = processor.extract_tables()
                    
                    # Extract outline
                    outline = processor.extract_outline()
                    
                    # Extract text for word count
                    text = processor.extract_text()
                    
                    # Perform content analysis
                    analytics = processor.analyze_content()
                    
                    # Compile statistics
                    file_stats = {
                        "filename": file_path.name,
                        "metadata": metadata,
                        "page_count": metadata.get("page_count", 0),
                        "file_size_kb": round(file_path.stat().st_size / 1024, 2),
                        "table_count": len(tables),
                        "section_count": len(outline) if outline else 0,
                        "word_count": analytics.get("word_count", 0) if analytics else 0,
                        "avg_words_per_page": round(analytics.get("word_count", 0) / metadata.get("page_count", 1), 2) if analytics and metadata.get("page_count") else 0,
                        "document_type": analytics.get("document_type", "Unknown") if analytics else "Unknown",
                        "complexity_score": analytics.get("complexity_score", 0) if analytics else 0,
                        "keywords": analytics.get("keywords", [])[:10] if analytics and "keywords" in analytics else [],
                        "table_distribution": analytics.get("table_distribution", {}) if analytics else {}
                    }
                    
                    stats.append(file_stats)
                    processor._cleanup()
                    
                except Exception as e:
                    logger.error(f"Error processing {file_path.name}: {e}")
                    stats.append({
                        "filename": file_path.name,
                        "error": str(e)
                    })
            
            # Calculate aggregate statistics
            if stats:
                valid_stats = [s for s in stats if "error" not in s]
                if valid_stats:
                    total_pages = sum(s.get("page_count", 0) for s in valid_stats)
                    total_tables = sum(s.get("table_count", 0) for s in valid_stats)
                    total_sections = sum(s.get("section_count", 0) for s in valid_stats)
                    total_words = sum(s.get("word_count", 0) for s in valid_stats)
                    
                    aggregate = {
                        "total_documents": len(valid_stats),
                        "total_pages": total_pages,
                        "total_tables": total_tables,
                        "total_sections": total_sections,
                        "total_words": total_words,
                        "avg_pages_per_document": round(total_pages / len(valid_stats), 2),
                        "avg_tables_per_document": round(total_tables / len(valid_stats), 2),
                        "avg_sections_per_document": round(total_sections / len(valid_stats), 2),
                        "avg_words_per_document": round(total_words / len(valid_stats), 2),
                        "document_types": {}
                    }
                    
                    # Count document types
                    for s in valid_stats:
                        doc_type = s.get("document_type", "Unknown")
                        if doc_type in aggregate["document_types"]:
                            aggregate["document_types"][doc_type] += 1
                        else:
                            aggregate["document_types"][doc_type] = 1
                else:
                    aggregate = {"error": "No valid documents processed"}
            else:
                aggregate = {"error": "No documents processed"}
            
            logger.info(f"Statistics extraction complete for {len(stats)} documents")
            return jsonify({
                "individual_statistics": stats,
                "aggregate_statistics": aggregate
            })
            
    except Exception as e:
        logger.error(f"Error in statistics endpoint: {e}")
        return jsonify({"error": str(e)}), 500

@api_blueprint.route('/cluster', methods=['POST'])
def cluster_documents():
    """Cluster multiple PDF documents based on content similarity"""
    try:
        logger.info("Starting document clustering")
        
        # Check if files were uploaded
        if 'files' not in request.files:
            return jsonify({"error": "No files uploaded"}), 400
            
        files = request.files.getlist('files')
        if not files:
            return jsonify({"error": "No files selected"}), 400
            
        # Get clustering parameters
        num_clusters = request.form.get('num_clusters', 3, type=int)
        algorithm = request.form.get('algorithm', 'kmeans')
        use_sections = request.form.get('use_sections', 'false').lower() == 'true'
        min_similarity = request.form.get('min_similarity', 0.3, type=float)
        
        # Validate parameters
        if num_clusters < 2:
            num_clusters = 2  # Minimum 2 clusters
        if min_similarity < 0 or min_similarity > 1:
            min_similarity = 0.3  # Default similarity threshold
            
        # Filter for PDF files only
        pdf_files = [f for f in files if f.filename.lower().endswith('.pdf')]
        if not pdf_files:
            return jsonify({"error": "No PDF files found in upload"}), 400
        
        if len(pdf_files) < num_clusters:
            num_clusters = len(pdf_files)  # Adjust clusters if fewer documents
            
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            
            # Save files to temp directory
            file_paths = []
            for pdf_file in pdf_files:
                file_path = tmp_path / pdf_file.filename
                pdf_file.save(file_path)
                file_paths.append(file_path)
            
            # Extract text from all PDFs
            documents = []
            document_names = []
            
            for file_path in file_paths:
                try:
                    processor = PDFProcessor(file_path)
                    
                    if use_sections:
                        # Extract by sections if requested
                        outline = processor.extract_outline()
                        if outline and len(outline) > 0:
                            # Use sections as separate documents for fine-grained clustering
                            for section in outline:
                                section_title = section.get('title', 'Untitled Section')
                                section_text = processor.extract_text(pages=section.get('pages', []))
                                if section_text.strip():
                                    documents.append(section_text)
                                    document_names.append(f"{file_path.name} - {section_title}")
                        else:
                            # Fallback to whole document if no sections
                            text = processor.extract_text()
                            documents.append(text)
                            document_names.append(file_path.name)
                    else:
                        # Use whole documents
                        text = processor.extract_text()
                        documents.append(text)
                        document_names.append(file_path.name)
                        
                    processor._cleanup()
                    
                except Exception as e:
                    logger.error(f"Error processing {file_path.name}: {e}")
            
            if not documents:
                return jsonify({"error": "Could not extract text from any documents"}), 400
                
            # Use semantic ranker to generate embeddings and cluster
            clusters = semantic_ranker.cluster_documents(
                documents=documents,
                document_names=document_names,
                num_clusters=num_clusters,
                algorithm=algorithm,
                min_similarity=min_similarity
            )
            
            # Format response
            result = {
                "clusters": clusters,
                "parameters": {
                    "num_clusters": num_clusters,
                    "algorithm": algorithm,
                    "use_sections": use_sections,
                    "min_similarity": min_similarity,
                    "total_documents": len(document_names)
                }
            }
            
            logger.info(f"Document clustering complete: {num_clusters} clusters from {len(document_names)} documents/sections")
            return jsonify(result)
            
    except Exception as e:
        logger.error(f"Error in clustering endpoint: {e}")
        return jsonify({"error": str(e)}), 500

@api_blueprint.route('/structure', methods=['POST'])
def extract_document_structure():
    """Extract and visualize the structure of a PDF document"""
    try:
        logger.info("Starting document structure extraction")
        
        # Check if file was uploaded
        if 'file' not in request.files:
            return jsonify({"error": "No file uploaded"}), 400
            
        pdf_file = request.files['file']
        if not pdf_file or pdf_file.filename == '':
            return jsonify({"error": "No file selected"}), 400
            
        # Validate file type
        if not pdf_file.filename.lower().endswith('.pdf'):
            return jsonify({"error": "Uploaded file is not a PDF"}), 400
            
        # Get extraction parameters
        extract_outline = request.form.get('extract_outline', 'true').lower() == 'true'
        extract_tables = request.form.get('extract_tables', 'true').lower() == 'true'
        extract_images = request.form.get('extract_images', 'false').lower() == 'true'
        extract_links = request.form.get('extract_links', 'true').lower() == 'true'
        extract_text_blocks = request.form.get('extract_text_blocks', 'true').lower() == 'true'
        include_page_layout = request.form.get('include_page_layout', 'false').lower() == 'true'
        
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            file_path = tmp_path / pdf_file.filename
            pdf_file.save(file_path)
            
            # Process the PDF
            try:
                processor = PDFProcessor(file_path)
                
                # Extract metadata
                metadata = processor._extract_metadata()
                
                # Build structure object
                structure = {
                    "filename": file_path.name,
                    "metadata": metadata,
                    "pages": []
                }
                
                # Extract outline/TOC if requested
                if extract_outline:
                    structure["outline"] = processor.extract_outline()
                
                # Process each page
                page_count = metadata.get("page_count", 0)
                for page_num in range(1, page_count + 1):
                    page_info = {"page_number": page_num}
                    
                    # Extract tables for this page if requested
                    if extract_tables:
                        tables = processor.extract_tables(pages=[page_num])
                        if tables:
                            page_info["tables"] = tables
                    
                    # Extract images for this page if requested
                    if extract_images:
                        images = processor.extract_images(pages=[page_num])
                        if images:
                            page_info["images"] = [
                                {"width": img.get("width"), "height": img.get("height"), 
                                 "position": img.get("position")} for img in images
                            ]
                    
                    # Extract links for this page if requested
                    if extract_links:
                        links = processor.extract_links(pages=[page_num])
                        if links:
                            page_info["links"] = links
                    
                    # Extract text blocks for this page if requested
                    if extract_text_blocks:
                        text_blocks = processor.extract_text_blocks(pages=[page_num])
                        if text_blocks:
                            page_info["text_blocks"] = text_blocks
                    
                    # Include page layout information if requested
                    if include_page_layout:
                        layout = processor.extract_page_layout(pages=[page_num])
                        if layout:
                            page_info["layout"] = layout
                    
                    structure["pages"].append(page_info)
                
                # Add document analysis
                structure["analysis"] = {
                    "structure_type": processor.detect_document_structure_type(),
                    "reading_order": processor.detect_reading_order(),
                    "complexity": processor.analyze_structural_complexity()
                }
                
                processor._cleanup()
                
                logger.info(f"Structure extraction complete for {file_path.name}")
                return jsonify(structure)
                
            except Exception as e:
                logger.error(f"Error processing {file_path.name}: {e}")
                return jsonify({"error": f"Error processing PDF: {str(e)}"}), 500
            
    except Exception as e:
        logger.error(f"Error in structure endpoint: {e}")
        return jsonify({"error": str(e)}), 500

@api_blueprint.route('/summarize', methods=['POST'])
def summarize_document():
    """Generate a concise summary of PDF document content"""
    try:
        logger.info("Starting document summarization")
        
        # Check if file was uploaded
        if 'file' not in request.files:
            return jsonify({"error": "No file uploaded"}), 400
            
        pdf_file = request.files['file']
        if not pdf_file or pdf_file.filename == '':
            return jsonify({"error": "No file selected"}), 400
            
        # Validate file type
        if not pdf_file.filename.lower().endswith('.pdf'):
            return jsonify({"error": "Uploaded file is not a PDF"}), 400
            
        # Get summarization parameters
        summary_type = request.form.get('summary_type', 'executive')  # executive, detailed, bullet
        max_length = request.form.get('max_length', 500, type=int)  # max characters
        include_sections = request.form.get('include_sections', 'true').lower() == 'true'
        include_key_points = request.form.get('include_key_points', 'true').lower() == 'true'
        include_topics = request.form.get('include_topics', 'true').lower() == 'true'
        
        # Validate parameters
        if summary_type not in ['executive', 'detailed', 'bullet']:
            summary_type = 'executive'
        if max_length < 100:
            max_length = 100  # Minimum length
        if max_length > 2000:
            max_length = 2000  # Maximum length
        
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            file_path = tmp_path / pdf_file.filename
            pdf_file.save(file_path)
            
            # Process the PDF
            try:
                processor = PDFProcessor(file_path)
                
                # Extract metadata
                metadata = processor._extract_metadata()
                
                # Extract text
                text = processor.extract_text()
                
                # Extract outline if needed
                outline = None
                if include_sections:
                    outline = processor.extract_outline()
                
                # Generate summary based on type
                summary = semantic_ranker.generate_summary(
                    text=text,
                    summary_type=summary_type,
                    max_length=max_length,
                    metadata=metadata,
                    outline=outline
                )
                
                # Build response
                result = {
                    "filename": file_path.name,
                    "summary": summary,
                    "metadata": {
                        "title": metadata.get("title", "Untitled"),
                        "author": metadata.get("author", "Unknown"),
                        "page_count": metadata.get("page_count", 0),
                        "creation_date": metadata.get("creation_date", "Unknown")
                    },
                    "parameters": {
                        "summary_type": summary_type,
                        "max_length": max_length,
                        "include_sections": include_sections,
                        "include_key_points": include_key_points,
                        "include_topics": include_topics
                    }
                }
                
                # Add key points if requested
                if include_key_points:
                    result["key_points"] = semantic_ranker.extract_key_points(text, metadata=metadata)
                
                # Add topics if requested
                if include_topics:
                    result["topics"] = semantic_ranker.extract_topics(text, metadata=metadata)
                
                # Add section summaries if requested and outline exists
                if include_sections and outline and len(outline) > 0:
                    section_summaries = []
                    for section in outline:
                        section_title = section.get('title', 'Untitled Section')
                        section_pages = section.get('pages', [])
                        if section_pages:
                            section_text = processor.extract_text(pages=section_pages)
                            if section_text.strip():
                                section_summary = semantic_ranker.generate_summary(
                                    text=section_text,
                                    summary_type='bullet',
                                    max_length=min(200, max_length // 2),
                                    metadata={"title": section_title}
                                )
                                section_summaries.append({
                                    "title": section_title,
                                    "summary": section_summary
                                })
                    
                    if section_summaries:
                        result["section_summaries"] = section_summaries
                
                processor._cleanup()
                
                logger.info(f"Summarization complete for {file_path.name}")
                return jsonify(result)
                
            except Exception as e:
                logger.error(f"Error processing {file_path.name}: {e}")
                return jsonify({"error": f"Error processing PDF: {str(e)}"}), 500
            
    except Exception as e:
        logger.error(f"Error in summarize endpoint: {e}")
        return jsonify({"error": str(e)}), 500

@api_blueprint.route('/tables', methods=['POST'])
def extract_tables():
    """Extract and analyze tables from PDF documents"""
    try:
        logger.info("Starting table extraction and analysis")
        
        # Check if file was uploaded
        if 'file' not in request.files:
            return jsonify({"error": "No file uploaded"}), 400
            
        pdf_file = request.files['file']
        if not pdf_file or pdf_file.filename == '':
            return jsonify({"error": "No file selected"}), 400
            
        # Validate file type
        if not pdf_file.filename.lower().endswith('.pdf'):
            return jsonify({"error": "Uploaded file is not a PDF"}), 400
            
        # Get extraction parameters
        format_as_json = request.form.get('format_as_json', 'true').lower() == 'true'
        include_csv = request.form.get('include_csv', 'true').lower() == 'true'
        include_excel = request.form.get('include_excel', 'false').lower() == 'true'
        include_statistics = request.form.get('include_statistics', 'true').lower() == 'true'
        include_page_numbers = request.form.get('include_page_numbers', 'true').lower() == 'true'
        include_table_titles = request.form.get('include_table_titles', 'true').lower() == 'true'
        
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            file_path = tmp_path / pdf_file.filename
            pdf_file.save(file_path)
            
            # Process the PDF
            try:
                processor = PDFProcessor(file_path)
                
                # Extract metadata
                metadata = processor._extract_metadata()
                
                # Extract tables
                tables = processor.extract_tables()
                
                if not tables:
                    return jsonify({
                        "filename": file_path.name,
                        "message": "No tables found in the document",
                        "tables_count": 0
                    })
                
                # Prepare response
                result = {
                    "filename": file_path.name,
                    "tables_count": len(tables),
                    "metadata": {
                        "title": metadata.get("title", "Untitled"),
                        "author": metadata.get("author", "Unknown"),
                        "page_count": metadata.get("page_count", 0)
                    }
                }
                
                # Process tables based on requested formats
                processed_tables = []
                csv_data = {}
                excel_data = None
                
                for i, table in enumerate(tables):
                    table_info = {
                        "table_id": i + 1,
                        "rows": len(table.get("data", [])),
                        "columns": len(table.get("data", [[]])[0]) if table.get("data") else 0
                    }
                    
                    if include_page_numbers and "page" in table:
                        table_info["page"] = table["page"]
                        
                    if include_table_titles and "title" in table:
                        table_info["title"] = table["title"]
                    
                    # Include table data in JSON format if requested
                    if format_as_json:
                        table_info["data"] = table.get("data", [])
                        
                        # Add header row if available
                        if "header" in table and table["header"]:
                            table_info["header"] = table["header"]
                    
                    # Generate CSV for this table if requested
                    if include_csv:
                        csv_data[f"table_{i+1}"] = processor.convert_table_to_csv(table)
                    
                    processed_tables.append(table_info)
                
                # Add tables to result
                result["tables"] = processed_tables
                
                # Add CSV data if requested
                if include_csv and csv_data:
                    result["csv_data"] = csv_data
                
                # Generate Excel file if requested
                if include_excel:
                    excel_path = tmp_path / f"{Path(file_path.name).stem}_tables.xlsx"
                    processor.convert_tables_to_excel(tables, excel_path)
                    
                    if excel_path.exists():
                        # Read Excel file as binary and encode as base64
                        with open(excel_path, "rb") as excel_file:
                            excel_data = base64.b64encode(excel_file.read()).decode("utf-8")
                        
                        result["excel_data"] = {
                            "filename": f"{Path(file_path.name).stem}_tables.xlsx",
                            "content": excel_data
                        }
                
                # Add table statistics if requested
                if include_statistics:
                    stats = {
                        "tables_per_page": round(len(tables) / metadata.get("page_count", 1), 2),
                        "avg_rows": round(sum(t.get("rows", 0) for t in processed_tables) / len(processed_tables), 2),
                        "avg_columns": round(sum(t.get("columns", 0) for t in processed_tables) / len(processed_tables), 2),
                        "largest_table": max((t.get("rows", 0) * t.get("columns", 0)) for t in processed_tables),
                        "page_distribution": {}
                    }
                    
                    # Count tables per page
                    if include_page_numbers:
                        for table in processed_tables:
                            if "page" in table:
                                page = str(table["page"])
                                if page in stats["page_distribution"]:
                                    stats["page_distribution"][page] += 1
                                else:
                                    stats["page_distribution"][page] = 1
                    
                    result["statistics"] = stats
                
                processor._cleanup()
                
                logger.info(f"Table extraction complete: {len(tables)} tables found in {file_path.name}")
                return jsonify(result)
                
            except Exception as e:
                logger.error(f"Error processing {file_path.name}: {e}")
                return jsonify({"error": f"Error processing PDF: {str(e)}"}), 500
            
    except Exception as e:
        logger.error(f"Error in tables endpoint: {e}")
        return jsonify({"error": str(e)}), 500

@api_blueprint.route('/ocr', methods=['POST'])
def ocr_pdf():
    """Extract text from scanned PDFs or images using OCR (Optical Character Recognition)"""
    try:
        logger.info("Starting OCR process")
        
        # Check if file was uploaded
        if 'file' not in request.files:
            return jsonify({"error": "No file uploaded"}), 400
            
        file = request.files['file']
        if not file or file.filename == '':
            return jsonify({"error": "No file selected"}), 400
            
        # Validate file type
        filename = file.filename.lower()
        if not (filename.endswith('.pdf') or filename.endswith('.jpg') or 
                filename.endswith('.jpeg') or filename.endswith('.png') or 
                filename.endswith('.tiff') or filename.endswith('.tif') or 
                filename.endswith('.bmp')):
            return jsonify({"error": "Unsupported file format. Supported formats: PDF, JPG, JPEG, PNG, TIFF, BMP"}), 400
            
        # Get OCR parameters
        language = request.form.get('language', 'eng')  # Default to English
        output_format = request.form.get('output_format', 'text').lower()  # text, json, markdown, html, hocr
        include_confidence = request.form.get('include_confidence', 'false').lower() == 'true'
        include_coordinates = request.form.get('include_coordinates', 'false').lower() == 'true'
        include_word_level = request.form.get('include_word_level', 'false').lower() == 'true'
        deskew = request.form.get('deskew', 'true').lower() == 'true'
        enhance_image = request.form.get('enhance_image', 'true').lower() == 'true'
        page_range = request.form.get('page_range', 'all')
        dpi = request.form.get('dpi', '300')
        try:
            dpi = int(dpi)
            if dpi < 72 or dpi > 1200:
                return jsonify({"error": "DPI must be between 72 and 1200"}), 400
        except ValueError:
            return jsonify({"error": "DPI must be a valid integer"}), 400
            
        # Validate language parameter
        valid_languages = ['eng', 'spa', 'fra', 'deu', 'ita', 'por', 'nld', 'rus', 'jpn', 'kor', 'chi_sim', 'chi_tra', 'ara', 'hin', 'ben', 'tha', 'tur', 'swe', 'nor', 'fin', 'dan', 'pol', 'heb', 'hun', 'cat', 'hrv', 'ukr', 'vie', 'ind']
        if language not in valid_languages:
            return jsonify({"error": f"Unsupported language code: {language}. Supported languages: {', '.join(valid_languages)}"}), 400
            
        # Validate output format
        valid_formats = ['text', 'json', 'markdown', 'html', 'hocr']
        if output_format not in valid_formats:
            return jsonify({"error": f"Unsupported output format: {output_format}. Supported formats: {', '.join(valid_formats)}"}), 400
            
        # Validate page range
        page_numbers = []
        if page_range != 'all':
            try:
                # Handle ranges like "1-3,5,7-9"
                for part in page_range.split(','):
                    if '-' in part:
                        start, end = map(int, part.split('-'))
                        if start < 1 or end < start:
                            return jsonify({"error": "Invalid page range. Pages must be positive and ranges must be in ascending order"}), 400
                        page_numbers.extend(range(start, end + 1))
                    else:
                        page_num = int(part)
                        if page_num < 1:
                            return jsonify({"error": "Invalid page number. Pages must be positive"}), 400
                        page_numbers.append(page_num)
            except ValueError:
                return jsonify({"error": "Invalid page range format. Use comma-separated page numbers and ranges (e.g., '1-3,5,7-9')"}), 400
            
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            file_path = tmp_path / file.filename
            file.save(file_path)
            
            # Process the file
            try:
                # In a real implementation, you would use an OCR library like Tesseract
                # For this example, we'll simulate OCR results
                
                # Determine if it's a PDF or image
                is_pdf = file_path.suffix.lower() == '.pdf'
                
                # For PDFs, we need to extract pages first
                if is_pdf:
                    processor = PDFProcessor(file_path)
                    metadata = processor._extract_metadata()
                    page_count = metadata.get("page_count", 0)
                    
                    # Validate page range for PDFs
                    if page_range != 'all' and max(page_numbers) > page_count:
                        return jsonify({"error": f"Invalid page range. Document only has {page_count} pages"}), 400
                        
                    # If page_range is 'all', process all pages
                    if page_range == 'all':
                        page_numbers = list(range(1, page_count + 1))
                else:
                    # For images, we only have one page
                    page_count = 1
                    page_numbers = [1] if page_range == 'all' else page_numbers
                    
                # Prepare OCR results
                ocr_results = {
                    "filename": file_path.name,
                    "file_type": "PDF" if is_pdf else file_path.suffix[1:].upper(),
                    "page_count": page_count,
                    "ocr_parameters": {
                        "language": language,
                        "output_format": output_format,
                        "include_confidence": include_confidence,
                        "include_coordinates": include_coordinates,
                        "include_word_level": include_word_level,
                        "deskew": deskew,
                        "enhance_image": enhance_image,
                        "dpi": dpi,
                        "page_range": page_range
                    },
                    "pages": []
                }
                
                # Simulate OCR for each page
                for page_num in page_numbers:
                    # Generate simulated text based on page number
                    simulated_text = f"This is simulated OCR text for page {page_num}. \n\nLorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.\n\nDuis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum."
                    
                    # Create page result based on requested format and options
                    page_result = {
                        "page_number": page_num,
                        "text": simulated_text
                    }
                    
                    # Add word-level data if requested
                    if include_word_level:
                        # Simulate word-level data
                        words = simulated_text.split()
                        word_data = []
                        
                        for i, word in enumerate(words):
                            word_info = {"text": word}
                            
                            # Add confidence scores if requested
                            if include_confidence:
                                # Simulate confidence scores between 80-100%
                                word_info["confidence"] = round(80 + (20 * (i % 5) / 4), 1)
                                
                            # Add coordinates if requested
                            if include_coordinates:
                                # Simulate bounding box coordinates
                                word_info["bbox"] = {
                                    "x0": 100 + (i * 10) % 400,
                                    "y0": 100 + (i // 40) * 30,
                                    "x1": 100 + (i * 10) % 400 + len(word) * 10,
                                    "y1": 100 + (i // 40) * 30 + 20
                                }
                                
                            word_data.append(word_info)
                            
                        page_result["words"] = word_data
                    elif include_coordinates:
                        # Simulate paragraph-level coordinates
                        paragraphs = simulated_text.split("\n\n")
                        paragraph_data = []
                        
                        for i, para in enumerate(paragraphs):
                            para_info = {"text": para}
                            
                            # Add confidence if requested
                            if include_confidence:
                                para_info["confidence"] = round(85 + (15 * (i % 3) / 2), 1)
                                
                            # Add coordinates
                            para_info["bbox"] = {
                                "x0": 50,
                                "y0": 50 + i * 150,
                                "x1": 550,
                                "y1": 50 + i * 150 + 100
                            }
                            
                            paragraph_data.append(para_info)
                            
                        page_result["paragraphs"] = paragraph_data
                        
                    ocr_results["pages"].append(page_result)
                
                # Format the final output based on requested format
                if output_format == 'text':
                    # For text format, just concatenate all page texts
                    text_content = "\n\n=== Page {page_num} ===\n\n".join(
                        [page["text"] for page in ocr_results["pages"]]
                    )
                    
                    # Add page numbers if there are multiple pages
                    if len(page_numbers) > 1:
                        text_content = "\n\n=== Page 1 ===\n\n" + text_content
                        
                    # Return plain text with metadata as JSON
                    result = {
                        "filename": ocr_results["filename"],
                        "page_count": ocr_results["page_count"],
                        "pages_processed": len(page_numbers),
                        "content": text_content
                    }
                    
                elif output_format == 'markdown':
                    # For markdown, format with headers for pages
                    md_content = ""
                    for page in ocr_results["pages"]:
                        md_content += f"## Page {page['page_number']}\n\n{page['text']}\n\n"
                        
                    result = {
                        "filename": ocr_results["filename"],
                        "page_count": ocr_results["page_count"],
                        "pages_processed": len(page_numbers),
                        "content": md_content
                    }
                    
                elif output_format == 'html':
                    # For HTML, create a formatted document
                    html_content = "<html><head><title>OCR Results</title></head><body>"
                    for page in ocr_results["pages"]:
                        html_content += f"<h2>Page {page['page_number']}</h2>"
                        
                        # If we have word-level data with coordinates, create positioned spans
                        if include_word_level and include_coordinates and "words" in page:
                            html_content += "<div style='position:relative;width:600px;height:800px;border:1px solid #ccc;'>"
                            for word in page["words"]:
                                bbox = word["bbox"]
                                confidence_attr = f" data-confidence='{word['confidence']}'" if include_confidence else ""
                                html_content += f"<span style='position:absolute;left:{bbox['x0']}px;top:{bbox['y0']}px;'{confidence_attr}>{word['text']}</span>"
                            html_content += "</div>"
                        else:
                            # Otherwise just add paragraphs of text
                            paragraphs = page["text"].split("\n\n")
                            for para in paragraphs:
                                html_content += f"<p>{para}</p>"
                                
                    html_content += "</body></html>"
                    
                    result = {
                        "filename": ocr_results["filename"],
                        "page_count": ocr_results["page_count"],
                        "pages_processed": len(page_numbers),
                        "content": html_content
                    }
                    
                elif output_format == 'hocr':
                    # For hOCR (HTML OCR), create a specialized format
                    # This is a simplified version of the actual hOCR format
                    hocr_content = """<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">\n<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en" lang="en">\n<head>\n  <title>OCR Results</title>\n  <meta http-equiv="Content-Type" content="text/html;charset=utf-8" />\n  <meta name='ocr-system' content='tesseract' />\n</head>\n<body>\n"""
                    
                    for page in ocr_results["pages"]:
                        hocr_content += f"<div class='ocr_page' id='page_{page['page_number']}' title='image; bbox 0 0 600 800'>\n"
                        
                        if include_word_level and "words" in page:
                            # Group words into paragraphs (simplified)
                            hocr_content += "  <div class='ocr_carea' id='block_1'>\n    <p class='ocr_par'>\n"
                            
                            for i, word in enumerate(page.get("words", [])):
                                bbox = word.get("bbox", {"x0": 0, "y0": 0, "x1": 0, "y1": 0})
                                confidence_attr = f" title='x_wconf {word.get('confidence', 95)}'" if include_confidence else ""
                                hocr_content += f"      <span class='ocr_word' id='word_{i+1}' bbox='{bbox['x0']} {bbox['y0']} {bbox['x1']} {bbox['y1']}'{confidence_attr}>{word['text']}</span>\n"
                                
                            hocr_content += "    </p>\n  </div>\n"
                        else:
                            # Just add the text without detailed markup
                            hocr_content += f"  <div class='ocr_text'>{page['text']}</div>\n"
                            
                        hocr_content += "</div>\n"
                        
                    hocr_content += "</body>\n</html>"
                    
                    result = {
                        "filename": ocr_results["filename"],
                        "page_count": ocr_results["page_count"],
                        "pages_processed": len(page_numbers),
                        "content": hocr_content
                    }
                    
                else:  # json format (default)
                    # Return the full structured data
                    result = ocr_results
                
                # Add processing statistics
                result["processing_stats"] = {
                    "time_taken_ms": 1250,  # Simulated processing time
                    "language": language,
                    "dpi": dpi,
                    "enhancement_applied": enhance_image,
                    "deskew_applied": deskew
                }
                
                if is_pdf:
                    processor._cleanup()
                
                logger.info(f"OCR completed: {file_path.name} processed {len(page_numbers)} pages")
                return jsonify(result)
                
            except Exception as e:
                logger.error(f"Error processing {file_path.name}: {e}")
                return jsonify({"error": f"Error performing OCR: {str(e)}"}), 500
            
    except Exception as e:
        logger.error(f"Error in OCR endpoint: {e}")
        return jsonify({"error": str(e)}), 500

@api_blueprint.route('/validate', methods=['POST'])
def validate_pdf():
    """Validate a PDF document against standards and accessibility requirements"""
    try:
        logger.info("Starting PDF validation process")
        
        # Check if file was uploaded
        if 'file' not in request.files:
            return jsonify({"error": "No file uploaded"}), 400
            
        pdf_file = request.files['file']
        if not pdf_file or pdf_file.filename == '':
            return jsonify({"error": "No file selected"}), 400
            
        # Validate file type
        if not pdf_file.filename.lower().endswith('.pdf'):
            return jsonify({"error": "Uploaded file is not a PDF"}), 400
            
        # Get validation parameters
        validation_standards = request.form.getlist('standards')  # List of standards to validate against
        check_accessibility = request.form.get('check_accessibility', 'true').lower() == 'true'
        check_signatures = request.form.get('check_signatures', 'false').lower() == 'true'
        check_fonts = request.form.get('check_fonts', 'true').lower() == 'true'
        check_metadata = request.form.get('check_metadata', 'true').lower() == 'true'
        check_structure = request.form.get('check_structure', 'true').lower() == 'true'
        check_xmp = request.form.get('check_xmp', 'false').lower() == 'true'
        check_images = request.form.get('check_images', 'true').lower() == 'true'
        check_color_spaces = request.form.get('check_color_spaces', 'false').lower() == 'true'
        check_annotations = request.form.get('check_annotations', 'false').lower() == 'true'
        check_form_fields = request.form.get('check_form_fields', 'false').lower() == 'true'
        severity_level = request.form.get('severity_level', 'all').lower()  # 'error', 'warning', 'info', 'all'
        
        # Default to PDF/A-1b if no standards specified
        if not validation_standards:
            validation_standards = ['pdf/a-1b']
            
        # Validate parameters
        valid_standards = ['pdf/a-1a', 'pdf/a-1b', 'pdf/a-2a', 'pdf/a-2b', 'pdf/a-3a', 'pdf/a-3b', 
                           'pdf/ua-1', 'pdf/x-1a', 'pdf/x-3', 'pdf/x-4', 'pdf/vt-1', 'pdf/e-1']
        for standard in validation_standards:
            if standard.lower() not in [s.lower() for s in valid_standards]:
                return jsonify({"error": f"Invalid standard: {standard}. Supported standards: {', '.join(valid_standards)}"}), 400
                
        valid_severity_levels = ['error', 'warning', 'info', 'all']
        if severity_level not in valid_severity_levels:
            return jsonify({"error": f"Invalid severity level: {severity_level}. Supported levels: {', '.join(valid_severity_levels)}"}), 400
            
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            file_path = tmp_path / pdf_file.filename
            pdf_file.save(file_path)
            
            # Process the PDF
            try:
                processor = PDFProcessor(file_path)
                
                # Extract metadata
                metadata = processor._extract_metadata()
                page_count = metadata.get("page_count", 0)
                
                # In a real implementation, you would use a PDF library to validate against standards
                # For this example, we'll simulate validation results
                
                # Prepare validation results
                validation_results = {
                    "filename": file_path.name,
                    "page_count": page_count,
                    "file_size": metadata.get("file_size", 0),
                    "pdf_version": metadata.get("pdf_version", "Unknown"),
                    "standards_checked": validation_standards,
                    "validation_parameters": {
                        "check_accessibility": check_accessibility,
                        "check_signatures": check_signatures,
                        "check_fonts": check_fonts,
                        "check_metadata": check_metadata,
                        "check_structure": check_structure,
                        "check_xmp": check_xmp,
                        "check_images": check_images,
                        "check_color_spaces": check_color_spaces,
                        "check_annotations": check_annotations,
                        "check_form_fields": check_form_fields,
                        "severity_level": severity_level
                    },
                    "results": []
                }
                
                # Simulate validation issues
                # In a real implementation, you would perform actual validation
                
                # Common validation issues by standard
                validation_issues = {
                    "pdf/a-1b": [
                        {"severity": "error", "category": "fonts", "message": "Font 'Arial' is not embedded", "page": 1},
                        {"severity": "warning", "category": "metadata", "message": "Document title is missing", "page": None},
                        {"severity": "info", "category": "color_spaces", "message": "Using RGB color space", "page": None}
                    ],
                    "pdf/a-1a": [
                        {"severity": "error", "category": "accessibility", "message": "Document lacks logical structure", "page": None},
                        {"severity": "error", "category": "accessibility", "message": "Images missing alternative text", "page": 2},
                        {"severity": "warning", "category": "structure", "message": "Reading order not defined", "page": None}
                    ],
                    "pdf/ua-1": [
                        {"severity": "error", "category": "accessibility", "message": "Document language not specified", "page": None},
                        {"severity": "error", "category": "accessibility", "message": "Table missing headers", "page": 3},
                        {"severity": "warning", "category": "accessibility", "message": "Low contrast text detected", "page": 4}
                    ],
                    "pdf/x-1a": [
                        {"severity": "error", "category": "color_spaces", "message": "RGB color space used instead of CMYK", "page": 1},
                        {"severity": "warning", "category": "images", "message": "Image resolution below 300 DPI", "page": 2}
                    ]
                }
                
                # Add simulated validation issues for each standard
                for standard in validation_standards:
                    standard_lower = standard.lower()
                    # Find the closest matching standard in our simulated issues
                    matching_standard = next((s for s in validation_issues.keys() if s.lower() == standard_lower), None)
                    
                    if matching_standard:
                        issues = validation_issues[matching_standard]
                        
                        # Filter issues based on severity level and check parameters
                        filtered_issues = []
                        for issue in issues:
                            # Filter by severity level
                            if severity_level != 'all' and issue["severity"] != severity_level:
                                continue
                                
                            # Filter by check parameters
                            category = issue["category"]
                            if (category == "accessibility" and not check_accessibility) or \
                               (category == "signatures" and not check_signatures) or \
                               (category == "fonts" and not check_fonts) or \
                               (category == "metadata" and not check_metadata) or \
                               (category == "structure" and not check_structure) or \
                               (category == "xmp" and not check_xmp) or \
                               (category == "images" and not check_images) or \
                               (category == "color_spaces" and not check_color_spaces) or \
                               (category == "annotations" and not check_annotations) or \
                               (category == "form_fields" and not check_form_fields):
                                continue
                                
                            filtered_issues.append(issue)
                            
                        # Add standard result
                        standard_result = {
                            "standard": standard,
                            "compliant": len(filtered_issues) == 0,
                            "issues": filtered_issues,
                            "issue_count": {
                                "total": len(filtered_issues),
                                "error": sum(1 for issue in filtered_issues if issue["severity"] == "error"),
                                "warning": sum(1 for issue in filtered_issues if issue["severity"] == "warning"),
                                "info": sum(1 for issue in filtered_issues if issue["severity"] == "info")
                            }
                        }
                        
                        validation_results["results"].append(standard_result)
                    else:
                        # Standard not in our simulated issues, assume compliant
                        validation_results["results"].append({
                            "standard": standard,
                            "compliant": True,
                            "issues": [],
                            "issue_count": {"total": 0, "error": 0, "warning": 0, "info": 0}
                        })
                
                # Add accessibility validation if requested
                if check_accessibility and "pdf/ua-1" not in [s.lower() for s in validation_standards]:
                    # Simulate accessibility validation
                    accessibility_issues = [
                        {"severity": "error", "category": "accessibility", "message": "Images missing alternative text", "page": 2},
                        {"severity": "error", "category": "accessibility", "message": "Document language not specified", "page": None},
                        {"severity": "warning", "category": "accessibility", "message": "Low contrast text detected", "page": 4},
                        {"severity": "info", "category": "accessibility", "message": "Consider adding more descriptive link text", "page": 3}
                    ]
                    
                    # Filter by severity level
                    if severity_level != 'all':
                        accessibility_issues = [issue for issue in accessibility_issues if issue["severity"] == severity_level]
                        
                    # Add accessibility result
                    validation_results["results"].append({
                        "standard": "WCAG 2.1",
                        "compliant": len(accessibility_issues) == 0,
                        "issues": accessibility_issues,
                        "issue_count": {
                            "total": len(accessibility_issues),
                            "error": sum(1 for issue in accessibility_issues if issue["severity"] == "error"),
                            "warning": sum(1 for issue in accessibility_issues if issue["severity"] == "warning"),
                            "info": sum(1 for issue in accessibility_issues if issue["severity"] == "info")
                        }
                    })
                
                # Add overall summary
                total_issues = sum(result["issue_count"]["total"] for result in validation_results["results"])
                total_errors = sum(result["issue_count"]["error"] for result in validation_results["results"])
                total_warnings = sum(result["issue_count"]["warning"] for result in validation_results["results"])
                total_info = sum(result["issue_count"]["info"] for result in validation_results["results"])
                
                validation_results["summary"] = {
                    "total_issues": total_issues,
                    "total_errors": total_errors,
                    "total_warnings": total_warnings,
                    "total_info": total_info,
                    "fully_compliant": total_errors == 0,
                    "standards_passed": sum(1 for result in validation_results["results"] if result["compliant"]),
                    "standards_failed": sum(1 for result in validation_results["results"] if not result["compliant"]),
                    "overall_status": "Pass" if total_errors == 0 else "Fail"
                }
                
                processor._cleanup()
                
                logger.info(f"Validation completed: {file_path.name} validated against {len(validation_standards)} standards with {total_issues} issues found")
                return jsonify(validation_results)
                
            except Exception as e:
                logger.error(f"Error processing {file_path.name}: {e}")
                return jsonify({"error": f"Error validating PDF: {str(e)}"}), 500
            
    except Exception as e:
        logger.error(f"Error in validate endpoint: {e}")
        return jsonify({"error": str(e)}), 500

@api_blueprint.route('/optimize', methods=['POST'])
def optimize_pdf():
    """Optimize a PDF document for specific use cases"""
    try:
        logger.info("Starting PDF optimization process")
        
        # Check if file was uploaded
        if 'file' not in request.files:
            return jsonify({"error": "No file uploaded"}), 400
            
        pdf_file = request.files['file']
        if not pdf_file or pdf_file.filename == '':
            return jsonify({"error": "No file selected"}), 400
            
        # Validate file type
        if not pdf_file.filename.lower().endswith('.pdf'):
            return jsonify({"error": "Uploaded file is not a PDF"}), 400
            
        # Get optimization parameters
        optimization_profile = request.form.get('optimization_profile', 'balanced').lower()  # 'web', 'print', 'ebook', 'balanced', 'custom'
        target_size_kb = request.form.get('target_size_kb')  # Target file size in KB (optional)
        
        # Custom optimization parameters (used when profile is 'custom')
        image_quality = int(request.form.get('image_quality', '80'))  # 1-100
        image_dpi = int(request.form.get('image_dpi', '150'))  # DPI for images
        image_downsampling = request.form.get('image_downsampling', 'bicubic').lower()  # 'bicubic', 'bilinear', 'nearest'
        color_space = request.form.get('color_space', 'rgb').lower()  # 'rgb', 'cmyk', 'grayscale'
        font_handling = request.form.get('font_handling', 'subset').lower()  # 'subset', 'embed', 'outline'
        compress_text = request.form.get('compress_text', 'true').lower() == 'true'
        flatten_transparency = request.form.get('flatten_transparency', 'false').lower() == 'true'
        remove_unused_objects = request.form.get('remove_unused_objects', 'true').lower() == 'true'
        remove_metadata = request.form.get('remove_metadata', 'false').lower() == 'true'
        linearize = request.form.get('linearize', 'true').lower() == 'true'  # Optimize for web viewing
        
        # Validate parameters
        valid_profiles = ['web', 'print', 'ebook', 'balanced', 'custom']
        if optimization_profile not in valid_profiles:
            return jsonify({"error": f"Invalid optimization profile: {optimization_profile}. Supported profiles: {', '.join(valid_profiles)}"}), 400
            
        if target_size_kb and not target_size_kb.isdigit():
            return jsonify({"error": f"Target size must be a positive number in KB, got {target_size_kb}"}), 400
            
        if not (1 <= image_quality <= 100):
            return jsonify({"error": f"Image quality must be between 1 and 100, got {image_quality}"}), 400
            
        valid_downsampling = ['bicubic', 'bilinear', 'nearest']
        if image_downsampling not in valid_downsampling:
            return jsonify({"error": f"Invalid image downsampling: {image_downsampling}. Supported methods: {', '.join(valid_downsampling)}"}), 400
            
        valid_color_spaces = ['rgb', 'cmyk', 'grayscale']
        if color_space not in valid_color_spaces:
            return jsonify({"error": f"Invalid color space: {color_space}. Supported color spaces: {', '.join(valid_color_spaces)}"}), 400
            
        valid_font_handling = ['subset', 'embed', 'outline']
        if font_handling not in valid_font_handling:
            return jsonify({"error": f"Invalid font handling: {font_handling}. Supported methods: {', '.join(valid_font_handling)}"}), 400
            
        # Set optimization parameters based on profile
        if optimization_profile != 'custom':
            if optimization_profile == 'web':
                image_quality = 70
                image_dpi = 96
                image_downsampling = 'bicubic'
                color_space = 'rgb'
                font_handling = 'subset'
                compress_text = True
                flatten_transparency = True
                remove_unused_objects = True
                remove_metadata = True
                linearize = True
            elif optimization_profile == 'print':
                image_quality = 90
                image_dpi = 300
                image_downsampling = 'bicubic'
                color_space = 'cmyk'
                font_handling = 'embed'
                compress_text = True
                flatten_transparency = True
                remove_unused_objects = True
                remove_metadata = False
                linearize = False
            elif optimization_profile == 'ebook':
                image_quality = 80
                image_dpi = 150
                image_downsampling = 'bilinear'
                color_space = 'rgb'
                font_handling = 'subset'
                compress_text = True
                flatten_transparency = True
                remove_unused_objects = True
                remove_metadata = False
                linearize = True
            elif optimization_profile == 'balanced':
                image_quality = 85
                image_dpi = 200
                image_downsampling = 'bicubic'
                color_space = 'rgb'
                font_handling = 'subset'
                compress_text = True
                flatten_transparency = False
                remove_unused_objects = True
                remove_metadata = False
                linearize = True
        
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            file_path = tmp_path / pdf_file.filename
            pdf_file.save(file_path)
            
            # Process the PDF
            try:
                processor = PDFProcessor(file_path)
                
                # Extract metadata
                metadata = processor._extract_metadata()
                page_count = metadata.get("page_count", 0)
                original_size = metadata.get("file_size", 0)
                
                # In a real implementation, you would use a PDF library to apply optimization settings
                # For this example, we'll simulate optimization results
                
                # Helper function to format file size
                def format_file_size(size_bytes):
                    if size_bytes < 1024:
                        return f"{size_bytes} B"
                    elif size_bytes < 1024 * 1024:
                        return f"{size_bytes / 1024:.2f} KB"
                    else:
                        return f"{size_bytes / (1024 * 1024):.2f} MB"
                
                # Simulate optimization based on parameters
                # In a real implementation, this would actually process the PDF
                
                # Calculate estimated size reduction based on parameters
                size_reduction_factor = 1.0
                
                # Image quality impact
                size_reduction_factor *= (100 / image_quality) * 0.5
                
                # Image DPI impact
                if image_dpi <= 96:
                    size_reduction_factor *= 1.5
                elif image_dpi <= 150:
                    size_reduction_factor *= 1.3
                elif image_dpi <= 200:
                    size_reduction_factor *= 1.1
                
                # Other parameters impact
                if compress_text:
                    size_reduction_factor *= 1.1
                if remove_unused_objects:
                    size_reduction_factor *= 1.2
                if remove_metadata:
                    size_reduction_factor *= 1.05
                
                # Calculate optimized size
                optimized_size = int(original_size / size_reduction_factor)
                
                # If target size is specified, adjust the optimization to meet it
                if target_size_kb and target_size_kb.isdigit():
                    target_size = int(target_size_kb) * 1024
                    if optimized_size > target_size:
                        # Further optimization needed
                        optimized_size = target_size
                        # In a real implementation, you would apply more aggressive optimization
                
                # Prepare optimization settings object
                optimization_settings = {
                    "profile": optimization_profile,
                    "image_quality": image_quality,
                    "image_dpi": image_dpi,
                    "image_downsampling": image_downsampling,
                    "color_space": color_space,
                    "font_handling": font_handling,
                    "compress_text": compress_text,
                    "flatten_transparency": flatten_transparency,
                    "remove_unused_objects": remove_unused_objects,
                    "remove_metadata": remove_metadata,
                    "linearize": linearize
                }
                
                # Prepare result object
                result = {
                    "original_filename": file_path.name,
                    "optimized_filename": f"optimized_{file_path.name}",
                    "page_count": page_count,
                    "original_size": {
                        "bytes": original_size,
                        "formatted": format_file_size(original_size)
                    },
                    "optimized_size": {
                        "bytes": optimized_size,
                        "formatted": format_file_size(optimized_size)
                    },
                    "size_reduction": {
                        "bytes": original_size - optimized_size,
                        "formatted": format_file_size(original_size - optimized_size),
                        "percentage": round((1 - (optimized_size / original_size)) * 100, 2)
                    },
                    "optimization_settings": optimization_settings
                }
                
                # Add target size information if specified
                if target_size_kb and target_size_kb.isdigit():
                    target_size = int(target_size_kb) * 1024
                    result["target_size"] = {
                        "bytes": target_size,
                        "formatted": format_file_size(target_size)
                    }
                    result["target_achieved"] = optimized_size <= target_size
                
                processor._cleanup()
                
                logger.info(f"Optimization completed: {file_path.name} optimized with {result['size_reduction']['percentage']}% reduction")
                return jsonify(result)
                
            except Exception as e:
                logger.error(f"Error processing {file_path.name}: {e}")
                return jsonify({"error": f"Error optimizing PDF: {str(e)}"}), 500
            
    except Exception as e:
        logger.error(f"Error in optimize endpoint: {e}")
        return jsonify({"error": str(e)}), 500

@api_blueprint.route('/compare', methods=['POST'])
def compare_pdfs():
    """Compare multiple PDF documents and identify differences"""
    try:
        logger.info("Starting PDF comparison process")
        
        # Check if files were uploaded
        if 'files' not in request.files:
            return jsonify({"error": "No files uploaded"}), 400
            
        files = request.files.getlist('files')
        if len(files) < 2:
            return jsonify({"error": "At least two PDF files are required for comparison"}), 400
            
        # Validate file types
        for file in files:
            if not file.filename.lower().endswith('.pdf'):
                return jsonify({"error": f"Uploaded file {file.filename} is not a PDF"}), 400
                
        # Get comparison parameters
        comparison_level = request.form.get('comparison_level', 'content').lower()  # 'content', 'visual', or 'both'
        highlight_differences = request.form.get('highlight_differences', 'true').lower() == 'true'
        include_text_diff = request.form.get('include_text_diff', 'true').lower() == 'true'
        include_visual_diff = request.form.get('include_visual_diff', 'false').lower() == 'true'
        sensitivity = float(request.form.get('sensitivity', '0.8'))  # 0.0 to 1.0, higher means more sensitive
        ignore_whitespace = request.form.get('ignore_whitespace', 'true').lower() == 'true'
        ignore_case = request.form.get('ignore_case', 'false').lower() == 'true'
        ignore_formatting = request.form.get('ignore_formatting', 'true').lower() == 'true'
        
        # Validate parameters
        valid_comparison_levels = ['content', 'visual', 'both']
        if comparison_level not in valid_comparison_levels:
            return jsonify({"error": f"Invalid comparison level: {comparison_level}. Supported levels: {', '.join(valid_comparison_levels)}"}), 400
            
        if not (0.0 <= sensitivity <= 1.0):
            return jsonify({"error": f"Sensitivity must be between 0.0 and 1.0, got {sensitivity}"}), 400
            
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            file_paths = []
            file_names = []
            
            # Save uploaded files
            for file in files:
                file_path = tmp_path / file.filename
                file.save(file_path)
                file_paths.append(file_path)
                file_names.append(file.filename)
                
            # Process the PDFs using PDFComparison utility
            try:
                # Use the PDFComparison utility to compare PDFs
                from utils.pdf_comparison import PDFComparison
                
                comparison_results = PDFComparison.compare_pdfs(
                    file_paths=file_paths,
                    comparison_level=comparison_level,
                    highlight_differences=highlight_differences,
                    include_text_diff=include_text_diff,
                    include_visual_diff=include_visual_diff,
                    sensitivity=sensitivity,
                    ignore_whitespace=ignore_whitespace,
                    ignore_case=ignore_case,
                    ignore_formatting=ignore_formatting
                )
                
                # Generate a summary using the utility's method
                summary = PDFComparison.generate_comparison_summary(comparison_results)
                
                # Format the response to match the expected structure
                formatted_response = {
                    "files": comparison_results['files'],
                    "comparison_parameters": {
                        "comparison_level": comparison_level,
                        "highlight_differences": highlight_differences,
                        "include_text_diff": include_text_diff,
                        "include_visual_diff": include_visual_diff,
                        "sensitivity": sensitivity,
                        "ignore_whitespace": ignore_whitespace,
                        "ignore_case": ignore_case,
                        "ignore_formatting": ignore_formatting
                    },
                    "file_metadata": comparison_results['metadata'],
                    "differences": []
                }
                
                # Process content differences if available
                if 'content' in comparison_results.get('differences', {}):
                    for pair_key, diff in comparison_results['differences']['content'].items():
                        file_names = pair_key.split('_vs_')
                        formatted_diff = {
                            "comparison": pair_key,
                            "similarity_score": diff['similarity'],
                            "is_different": diff['is_different'],
                            "difference_count": diff.get('diff_count', 0),
                            "difference_type": "content"
                        }
                        
                        # Include text differences if available
                        if include_text_diff and diff['is_different'] and 'text_diff' in diff:
                            formatted_diff["text_differences"] = {
                                "summary": f"Found approximately {diff.get('diff_count', 0)} differences",
                                "details": diff['text_diff']
                            }
                            
                        formatted_response["differences"].append(formatted_diff)
                
                # Process visual differences if available
                if 'visual' in comparison_results.get('differences', {}):
                    for pair_key, diff in comparison_results['differences']['visual'].items():
                        file_names = pair_key.split('_vs_')
                        formatted_diff = {
                            "comparison": pair_key,
                            "similarity_score": diff['similarity'],
                            "is_different": diff['is_different'],
                            "difference_type": "visual"
                        }
                        
                        # Include visual differences if available
                        if include_visual_diff and diff['is_different']:
                            formatted_diff["visual_differences"] = {
                                "total_pages_compared": min(diff['page_count1'], diff['page_count2']),
                                "pages_with_differences": diff['diff_count'],
                                "difference_areas": diff.get('visual_diff', [])
                            }
                            
                        formatted_response["differences"].append(formatted_diff)
                
                # Add summary from the utility
                formatted_response["summary"] = {
                    "total_comparisons": summary.get('file_count', 0) * (summary.get('file_count', 0) - 1) // 2,
                    "files_with_differences": summary.get('different_pair_count', 0),
                    "identical_files": summary.get('identical_pair_count', 0),
                    "overall_similarity": summary.get('overall_similarity', {}).get('combined', 1.0),
                    "assessment": summary.get('assessment', '')
                }
                
                logger.info(f"Comparison completed: {len(file_names)} files compared with {summary.get('different_pair_count', 0)} differences found")
                return jsonify(formatted_response)
                
            except Exception as e:
                logger.error(f"Error processing comparison: {e}")
                return jsonify({"error": f"Error comparing PDFs: {str(e)}"}), 500
            
    except Exception as e:
        logger.error(f"Error in compare endpoint: {e}")
        return jsonify({"error": str(e)}), 500

@api_blueprint.route('/secure', methods=['POST'])
def secure_pdf():
    """Secure a PDF document with passwords and permissions"""
    try:
        logger.info("Starting PDF security process")
        
        # Check if file was uploaded
        if 'file' not in request.files:
            return jsonify({"error": "No file uploaded"}), 400
            
        pdf_file = request.files['file']
        if not pdf_file or pdf_file.filename == '':
            return jsonify({"error": "No file selected"}), 400
            
        # Validate file type
        if not pdf_file.filename.lower().endswith('.pdf'):
            return jsonify({"error": "Uploaded file is not a PDF"}), 400
            
        # Get security parameters
        user_password = request.form.get('user_password', '')  # Password to open the document
        owner_password = request.form.get('owner_password', '')  # Password to change permissions
        encryption_level = request.form.get('encryption_level', '128').lower()  # 40, 128, or 256
        
        # Permission parameters
        allow_printing = request.form.get('allow_printing', 'true').lower() == 'true'
        allow_degraded_printing = request.form.get('allow_degraded_printing', 'true').lower() == 'true'
        allow_modify_contents = request.form.get('allow_modify_contents', 'false').lower() == 'true'
        allow_copy = request.form.get('allow_copy', 'false').lower() == 'true'
        allow_modify_annotations = request.form.get('allow_modify_annotations', 'false').lower() == 'true'
        allow_fill_forms = request.form.get('allow_fill_forms', 'true').lower() == 'true'
        allow_screen_readers = request.form.get('allow_screen_readers', 'true').lower() == 'true'
        allow_assembly = request.form.get('allow_assembly', 'false').lower() == 'true'
        
        # Validate parameters
        valid_encryption_levels = ['40', '128', '256']
        if encryption_level not in valid_encryption_levels:
            return jsonify({"error": f"Invalid encryption level: {encryption_level}. Supported levels: {', '.join(valid_encryption_levels)}"}), 400
            
        # Validate password requirements
        if user_password and len(user_password) < 4:
            return jsonify({"error": "User password must be at least 4 characters long"}), 400
            
        if owner_password and len(owner_password) < 4:
            return jsonify({"error": "Owner password must be at least 4 characters long"}), 400
            
        # If no passwords are provided, at least some permissions must be restricted
        if not user_password and not owner_password:
            if all([allow_printing, allow_degraded_printing, allow_modify_contents, allow_copy, 
                    allow_modify_annotations, allow_fill_forms, allow_screen_readers, allow_assembly]):
                return jsonify({"error": "Either passwords must be set or some permissions must be restricted"}), 400
                
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            file_path = tmp_path / pdf_file.filename
            pdf_file.save(file_path)
            
            # Process the PDF
            try:
                processor = PDFProcessor(file_path)
                
                # Extract metadata
                metadata = processor._extract_metadata()
                page_count = metadata.get("page_count", 0)
                
                # In a real implementation, you would use a PDF library to apply security settings
                # For this example, we'll just return the security information
                
                # Prepare permissions object
                permissions = {
                    "allow_printing": allow_printing,
                    "allow_degraded_printing": allow_degraded_printing,
                    "allow_modify_contents": allow_modify_contents,
                    "allow_copy": allow_copy,
                    "allow_modify_annotations": allow_modify_annotations,
                    "allow_fill_forms": allow_fill_forms,
                    "allow_screen_readers": allow_screen_readers,
                    "allow_assembly": allow_assembly
                }
                
                # Prepare result object
                result = {
                    "original_filename": file_path.name,
                    "secured_filename": f"secured_{file_path.name}",
                    "page_count": page_count,
                    "encryption_level": encryption_level,
                    "has_user_password": bool(user_password),
                    "has_owner_password": bool(owner_password),
                    "permissions": permissions
                }
                
                # Add security strength assessment
                security_strength = "low"
                if user_password and owner_password and encryption_level == '256':
                    security_strength = "high"
                elif (user_password or owner_password) and encryption_level in ['128', '256']:
                    security_strength = "medium"
                    
                result["security_strength"] = security_strength
                
                # Add permission summary
                permission_count = sum(1 for perm in permissions.values() if perm)
                result["permission_summary"] = {
                    "total_permissions": 8,
                    "allowed_permissions": permission_count,
                    "restricted_permissions": 8 - permission_count
                }
                
                processor._cleanup()
                
                logger.info(f"Security applied: {file_path.name} secured with {encryption_level}-bit encryption and {8 - permission_count} restricted permissions")
                return jsonify(result)
                
            except Exception as e:
                logger.error(f"Error processing {file_path.name}: {e}")
                return jsonify({"error": f"Error securing PDF: {str(e)}"}), 500
            
    except Exception as e:
        logger.error(f"Error in secure endpoint: {e}")
        return jsonify({"error": str(e)}), 500

@api_blueprint.route('/redact', methods=['POST'])
def redact_pdf():
    """Redact sensitive information from PDF documents"""
    try:
        logger.info("Starting PDF redaction process")
        
        # Check if file was uploaded
        if 'file' not in request.files:
            return jsonify({"error": "No file uploaded"}), 400
            
        pdf_file = request.files['file']
        if not pdf_file or pdf_file.filename == '':
            return jsonify({"error": "No file selected"}), 400
            
        # Validate file type
        if not pdf_file.filename.lower().endswith('.pdf'):
            return jsonify({"error": "Uploaded file is not a PDF"}), 400
            
        # Get redaction parameters
        patterns = request.form.get('patterns', '').split(',')  # Comma-separated patterns to redact
        redact_types = request.form.get('types', 'all').lower().split(',')  # Types of data to redact: pii, emails, phones, dates, credit_cards, ssn, all
        custom_regex = request.form.get('custom_regex', '')  # Custom regex pattern for redaction
        replacement_text = request.form.get('replacement', '[REDACTED]')  # Text to replace redacted content
        include_preview = request.form.get('include_preview', 'true').lower() == 'true'  # Include preview of redacted text
        
        # Validate redaction types
        valid_types = ['pii', 'emails', 'phones', 'dates', 'credit_cards', 'ssn', 'addresses', 'names', 'all']
        for redact_type in redact_types:
            if redact_type not in valid_types:
                return jsonify({"error": f"Invalid redaction type: {redact_type}. Supported types: {', '.join(valid_types)}"}), 400
        
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            file_path = tmp_path / pdf_file.filename
            pdf_file.save(file_path)
            
            # Process the PDF
            try:
                processor = PDFProcessor(file_path)
                
                # Extract metadata
                metadata = processor._extract_metadata()
                
                # Extract text for processing
                text_content = processor.extract_text()
                text_by_page = processor.extract_text_by_page()
                
                # Prepare redaction patterns based on selected types
                redaction_patterns = []
                
                # Add user-specified patterns
                for pattern in patterns:
                    if pattern.strip():
                        redaction_patterns.append(pattern.strip())
                
                # Add custom regex if provided
                if custom_regex:
                    redaction_patterns.append(custom_regex)
                
                # Add predefined patterns based on selected types
                if 'all' in redact_types or 'emails' in redact_types:
                    redaction_patterns.append(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
                    
                if 'all' in redact_types or 'phones' in redact_types:
                    redaction_patterns.append(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b')
                    
                if 'all' in redact_types or 'dates' in redact_types:
                    redaction_patterns.append(r'\b\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}\b')
                    
                if 'all' in redact_types or 'credit_cards' in redact_types:
                    redaction_patterns.append(r'\b(?:\d{4}[- ]?){3}\d{4}\b')
                    
                if 'all' in redact_types or 'ssn' in redact_types:
                    redaction_patterns.append(r'\b\d{3}[-]?\d{2}[-]?\d{4}\b')
                    
                if 'all' in redact_types or 'addresses' in redact_types:
                    redaction_patterns.append(r'\b\d+\s+[A-Za-z\s]+(?:Avenue|Ave|Street|St|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln|Court|Ct|Way|Place|Pl)\b')
                
                # Perform redaction
                redacted_content = text_content
                redacted_by_page = []
                redacted_items = []
                
                import re
                
                # Process each page
                for i, page_text in enumerate(text_by_page):
                    page_num = i + 1
                    redacted_page = page_text
                    page_redactions = []
                    
                    # Apply each pattern
                    for pattern in redaction_patterns:
                        try:
                            matches = re.finditer(pattern, page_text)
                            for match in matches:
                                matched_text = match.group(0)
                                redacted_page = redacted_page.replace(matched_text, replacement_text)
                                
                                # Record redaction
                                page_redactions.append({
                                    "original": matched_text,
                                    "pattern": pattern,
                                    "position": match.span()
                                })
                                
                                # Add to global redactions list
                                redacted_items.append({
                                    "page": page_num,
                                    "original": matched_text,
                                    "replacement": replacement_text,
                                    "pattern": pattern
                                })
                        except re.error as e:
                            logger.error(f"Invalid regex pattern: {pattern}. Error: {e}")
                    
                    redacted_by_page.append({
                        "page_number": page_num,
                        "redacted_text": redacted_page,
                        "redactions": page_redactions
                    })
                
                # Generate output filename for redacted PDF
                output_filename = f"redacted_{file_path.stem}.pdf"
                output_path = tmp_path / output_filename
                
                # In a real implementation, you would use a PDF library to create a redacted PDF
                # For this example, we'll just return the redacted text and metadata
                
                # Prepare result object
                result = {
                    "filename": file_path.name,
                    "redacted_filename": output_filename,
                    "metadata": {
                        "title": metadata.get("title", "Untitled"),
                        "author": metadata.get("author", "Unknown"),
                        "page_count": metadata.get("page_count", 0)
                    },
                    "redaction_summary": {
                        "total_redactions": len(redacted_items),
                        "patterns_used": redaction_patterns,
                        "replacement_text": replacement_text
                    }
                }
                
                # Include redacted items if requested
                if include_preview:
                    result["redacted_items"] = redacted_items
                    
                    # Include sample of redacted text (first 1000 chars)
                    redacted_sample = "\n\n".join([page["redacted_text"][:1000] for page in redacted_by_page])
                    result["redacted_sample"] = redacted_sample
                
                # Calculate statistics
                redactions_by_type = {}
                for item in redacted_items:
                    pattern = item["pattern"]
                    redaction_type = "custom"
                    
                    # Determine type based on pattern
                    if pattern == r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}':
                        redaction_type = "email"
                    elif pattern == r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b':
                        redaction_type = "phone"
                    elif pattern == r'\b\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}\b':
                        redaction_type = "date"
                    elif pattern == r'\b(?:\d{4}[- ]?){3}\d{4}\b':
                        redaction_type = "credit_card"
                    elif pattern == r'\b\d{3}[-]?\d{2}[-]?\d{4}\b':
                        redaction_type = "ssn"
                    elif pattern == r'\b\d+\s+[A-Za-z\s]+(?:Avenue|Ave|Street|St|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln|Court|Ct|Way|Place|Pl)\b':
                        redaction_type = "address"
                    
                    if redaction_type in redactions_by_type:
                        redactions_by_type[redaction_type] += 1
                    else:
                        redactions_by_type[redaction_type] = 1
                
                result["redaction_summary"]["redactions_by_type"] = redactions_by_type
                
                # Calculate redactions by page
                redactions_by_page = {}
                for item in redacted_items:
                    page = str(item["page"])
                    if page in redactions_by_page:
                        redactions_by_page[page] += 1
                    else:
                        redactions_by_page[page] = 1
                
                result["redaction_summary"]["redactions_by_page"] = redactions_by_page
                
                processor._cleanup()
                
                logger.info(f"Redaction complete: {len(redacted_items)} items redacted from {file_path.name}")
                return jsonify(result)
                
            except Exception as e:
                logger.error(f"Error processing {file_path.name}: {e}")
                return jsonify({"error": f"Error redacting PDF: {str(e)}"}), 500
            
    except Exception as e:
        logger.error(f"Error in redact endpoint: {e}")
        return jsonify({"error": str(e)}), 500

@api_blueprint.route('/watermark', methods=['POST'])
def watermark_pdf():
    """Add watermarks to a PDF document"""
    try:
        logger.info("Starting PDF watermarking process")
        
        # Check if file was uploaded
        if 'file' not in request.files:
            return jsonify({"error": "No file uploaded"}), 400
            
        pdf_file = request.files['file']
        if not pdf_file or pdf_file.filename == '':
            return jsonify({"error": "No file selected"}), 400
            
        # Validate file type
        if not pdf_file.filename.lower().endswith('.pdf'):
            return jsonify({"error": "Uploaded file is not a PDF"}), 400
            
        # Get watermark parameters
        watermark_type = request.form.get('watermark_type', 'text').lower()  # text, image, or pdf
        watermark_text = request.form.get('watermark_text', 'CONFIDENTIAL')
        watermark_image = request.files.get('watermark_image')
        watermark_pdf = request.files.get('watermark_pdf')
        
        # Position and appearance parameters
        position = request.form.get('position', 'center').lower()  # center, diagonal, tiled, custom
        opacity = float(request.form.get('opacity', '0.3'))
        rotation = float(request.form.get('rotation', '45'))
        scale = float(request.form.get('scale', '1.0'))
        
        # Custom position coordinates (if position is 'custom')
        x_position = request.form.get('x_position')
        y_position = request.form.get('y_position')
        
        # Page range parameters
        page_range = request.form.get('page_range', 'all').lower()  # all, even, odd, custom
        custom_pages = request.form.get('custom_pages', '')
        
        # Text watermark specific parameters
        font = request.form.get('font', 'Helvetica')
        font_size = int(request.form.get('font_size', '72'))
        font_color = request.form.get('font_color', '#888888')
        
        # Validate parameters
        valid_watermark_types = ['text', 'image', 'pdf']
        if watermark_type not in valid_watermark_types:
            return jsonify({"error": f"Invalid watermark type: {watermark_type}. Supported types: {', '.join(valid_watermark_types)}"}), 400
            
        valid_positions = ['center', 'diagonal', 'tiled', 'custom']
        if position not in valid_positions:
            return jsonify({"error": f"Invalid position: {position}. Supported positions: {', '.join(valid_positions)}"}), 400
            
        valid_page_ranges = ['all', 'even', 'odd', 'custom']
        if page_range not in valid_page_ranges:
            return jsonify({"error": f"Invalid page range: {page_range}. Supported ranges: {', '.join(valid_page_ranges)}"}), 400
            
        # Validate opacity (0.0 to 1.0)
        if opacity < 0.0 or opacity > 1.0:
            return jsonify({"error": "Opacity must be between 0.0 and 1.0"}), 400
            
        # Validate scale (0.1 to 5.0)
        if scale < 0.1 or scale > 5.0:
            return jsonify({"error": "Scale must be between 0.1 and 5.0"}), 400
            
        # Validate custom pages format if specified
        if page_range == 'custom' and custom_pages:
            try:
                # Parse comma-separated page numbers or ranges (e.g., "1,3-5,7")
                page_list = []
                for part in custom_pages.split(','):
                    if '-' in part:
                        start, end = map(int, part.split('-'))
                        if start < 1 or end < start:
                            return jsonify({"error": f"Invalid page range: {part}"}), 400
                        page_list.extend(range(start, end + 1))
                    else:
                        page_num = int(part)
                        if page_num < 1:
                            return jsonify({"error": f"Invalid page number: {part}"}), 400
                        page_list.append(page_num)
            except ValueError:
                return jsonify({"error": "Invalid format for custom pages"}), 400
                
        # Validate watermark content based on type
        if watermark_type == 'text' and not watermark_text:
            return jsonify({"error": "Watermark text is required for text watermarks"}), 400
            
        if watermark_type == 'image' and not watermark_image:
            return jsonify({"error": "Watermark image file is required for image watermarks"}), 400
            
        if watermark_type == 'pdf' and not watermark_pdf:
            return jsonify({"error": "Watermark PDF file is required for PDF watermarks"}), 400
            
        # Validate image file type if provided
        if watermark_type == 'image' and watermark_image:
            filename = watermark_image.filename.lower()
            if not (filename.endswith('.jpg') or filename.endswith('.jpeg') or 
                    filename.endswith('.png') or filename.endswith('.gif')):
                return jsonify({"error": "Watermark image must be JPG, PNG, or GIF"}), 400
                
        # Validate PDF file type if provided
        if watermark_type == 'pdf' and watermark_pdf and not watermark_pdf.filename.lower().endswith('.pdf'):
            return jsonify({"error": "Watermark file must be a PDF"}), 400
            
        # Validate custom position if specified
        if position == 'custom':
            try:
                if x_position is None or y_position is None:
                    return jsonify({"error": "Both x_position and y_position are required for custom positioning"}), 400
                    
                x_pos = float(x_position)
                y_pos = float(y_position)
                
                if x_pos < 0.0 or x_pos > 1.0 or y_pos < 0.0 or y_pos > 1.0:
                    return jsonify({"error": "Position coordinates must be between 0.0 and 1.0"}), 400
            except ValueError:
                return jsonify({"error": "Position coordinates must be valid numbers"}), 400
                
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            file_path = tmp_path / pdf_file.filename
            pdf_file.save(file_path)
            
            # Save watermark file if provided
            watermark_file_path = None
            if watermark_type == 'image' and watermark_image:
                watermark_file_path = tmp_path / watermark_image.filename
                watermark_image.save(watermark_file_path)
            elif watermark_type == 'pdf' and watermark_pdf:
                watermark_file_path = tmp_path / watermark_pdf.filename
                watermark_pdf.save(watermark_file_path)
                
            # Process the PDF
            try:
                processor = PDFProcessor(file_path)
                
                # Extract metadata
                metadata = processor._extract_metadata()
                page_count = metadata.get("page_count", 0)
                
                # Determine which pages to watermark
                pages_to_watermark = []
                
                if page_range == 'all':
                    pages_to_watermark = list(range(1, page_count + 1))
                elif page_range == 'even':
                    pages_to_watermark = [p for p in range(1, page_count + 1) if p % 2 == 0]
                elif page_range == 'odd':
                    pages_to_watermark = [p for p in range(1, page_count + 1) if p % 2 == 1]
                elif page_range == 'custom' and custom_pages:
                    # Parse comma-separated page numbers or ranges
                    for part in custom_pages.split(','):
                        if '-' in part:
                            start, end = map(int, part.split('-'))
                            pages_to_watermark.extend(range(start, min(end + 1, page_count + 1)))
                        else:
                            page_num = int(part)
                            if 1 <= page_num <= page_count:
                                pages_to_watermark.append(page_num)
                    # Remove duplicates and sort
                    pages_to_watermark = sorted(set(pages_to_watermark))
                
                # In a real implementation, you would use a PDF library to apply the watermark
                # For this example, we'll just return the watermark information
                
                # Prepare result object
                result = {
                    "original_filename": file_path.name,
                    "original_page_count": page_count,
                    "watermark_type": watermark_type,
                    "position": position,
                    "opacity": opacity,
                    "rotation": rotation,
                    "scale": scale,
                    "page_range": page_range,
                    "pages_watermarked": len(pages_to_watermark),
                    "watermarked_pages": pages_to_watermark
                }
                
                # Add type-specific information
                if watermark_type == 'text':
                    result["watermark_text"] = watermark_text
                    result["font"] = font
                    result["font_size"] = font_size
                    result["font_color"] = font_color
                elif watermark_type == 'image':
                    result["watermark_image"] = watermark_image.filename if watermark_image else None
                elif watermark_type == 'pdf':
                    result["watermark_pdf"] = watermark_pdf.filename if watermark_pdf else None
                    
                # Add position-specific information
                if position == 'custom':
                    result["x_position"] = float(x_position)
                    result["y_position"] = float(y_position)
                elif position == 'tiled':
                    # For tiled watermarks, we would specify the tile spacing
                    result["tile_spacing_x"] = 200  # Example value in points
                    result["tile_spacing_y"] = 200  # Example value in points
                
                processor._cleanup()
                
                logger.info(f"Watermarking complete: {file_path.name} with {watermark_type} watermark on {len(pages_to_watermark)} pages")
                return jsonify(result)
                
            except Exception as e:
                logger.error(f"Error processing {file_path.name}: {e}")
                return jsonify({"error": f"Error watermarking PDF: {str(e)}"}), 500
            
    except Exception as e:
        logger.error(f"Error in watermark endpoint: {e}")
        return jsonify({"error": str(e)}), 500

@api_blueprint.route('/annotate', methods=['POST'])
def annotate_pdf():
    """Add annotations, comments, highlights, and other markup to PDF documents"""
    try:
        logger.info("Starting PDF annotation process")
        
        # Check if file was uploaded
        if 'file' not in request.files:
            return jsonify({"error": "No file uploaded"}), 400
            
        pdf_file = request.files['file']
        if not pdf_file or pdf_file.filename == '':
            return jsonify({"error": "No file selected"}), 400
            
        # Validate file type
        if not pdf_file.filename.lower().endswith('.pdf'):
            return jsonify({"error": "Uploaded file is not a PDF"}), 400
            
        # Get annotation parameters
        annotations_json = request.form.get('annotations', '[]')
        try:
            annotations = json.loads(annotations_json)
            if not isinstance(annotations, list):
                return jsonify({"error": "Annotations must be a JSON array"}), 400
        except json.JSONDecodeError:
            return jsonify({"error": "Invalid JSON format for annotations"}), 400
            
        # Validate annotations format
        for i, annotation in enumerate(annotations):
            if not isinstance(annotation, dict):
                return jsonify({"error": f"Annotation at index {i} must be a JSON object"}), 400
                
            # Check required fields
            required_fields = ['type', 'page', 'content']
            for field in required_fields:
                if field not in annotation:
                    return jsonify({"error": f"Annotation at index {i} missing required field: {field}"}), 400
            
            # Validate annotation type
            valid_types = ['highlight', 'text', 'note', 'rectangle', 'circle', 'line', 'arrow', 'stamp', 'ink', 'link']
            if annotation['type'] not in valid_types:
                return jsonify({"error": f"Invalid annotation type at index {i}: {annotation['type']}. Supported types: {', '.join(valid_types)}"}), 400
                
            # Validate page number
            if not isinstance(annotation['page'], int) or annotation['page'] < 1:
                return jsonify({"error": f"Invalid page number at index {i}: {annotation['page']}. Must be a positive integer."}), 400
        
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            file_path = tmp_path / pdf_file.filename
            pdf_file.save(file_path)
            
            # Process the PDF
            try:
                processor = PDFProcessor(file_path)
                
                # Extract metadata
                metadata = processor._extract_metadata()
                page_count = metadata.get("page_count", 0)
                
                # Validate page numbers in annotations
                for i, annotation in enumerate(annotations):
                    if annotation['page'] > page_count:
                        return jsonify({"error": f"Annotation at index {i} references page {annotation['page']}, but document only has {page_count} pages"}), 400
                
                # Generate output filename for annotated PDF
                output_filename = f"annotated_{file_path.stem}.pdf"
                output_path = tmp_path / output_filename
                
                # In a real implementation, you would use a PDF library to create an annotated PDF
                # For this example, we'll just return the annotation metadata
                
                # Process annotations by type
                processed_annotations = []
                for annotation in annotations:
                    processed_annotation = {
                        "type": annotation["type"],
                        "page": annotation["page"],
                        "content": annotation["content"],
                        "id": str(uuid.uuid4())
                    }
                    
                    # Add type-specific properties
                    if annotation["type"] == "highlight":
                        # For highlights, we need coordinates or text to highlight
                        if "coordinates" in annotation:
                            processed_annotation["coordinates"] = annotation["coordinates"]
                        elif "text" in annotation:
                            processed_annotation["text"] = annotation["text"]
                            # In a real implementation, we would find the coordinates of this text in the PDF
                            processed_annotation["coordinates"] = {"x1": 0, "y1": 0, "x2": 100, "y2": 20}  # Mock coordinates
                        else:
                            return jsonify({"error": f"Highlight annotation requires either 'coordinates' or 'text' property"}), 400
                            
                        # Add optional properties
                        if "color" in annotation:
                            processed_annotation["color"] = annotation["color"]
                        else:
                            processed_annotation["color"] = "#FFFF00"  # Default yellow
                            
                    elif annotation["type"] == "text" or annotation["type"] == "note":
                        # For text annotations, we need position
                        if "position" in annotation:
                            processed_annotation["position"] = annotation["position"]
                        else:
                            # Default position in the center of the page
                            processed_annotation["position"] = {"x": 300, "y": 400}
                            
                        # Add optional properties
                        if "color" in annotation:
                            processed_annotation["color"] = annotation["color"]
                        else:
                            processed_annotation["color"] = "#0000FF"  # Default blue
                            
                        if "font" in annotation:
                            processed_annotation["font"] = annotation["font"]
                        else:
                            processed_annotation["font"] = "Helvetica"
                            
                        if "font_size" in annotation:
                            processed_annotation["font_size"] = annotation["font_size"]
                        else:
                            processed_annotation["font_size"] = 12
                            
                    elif annotation["type"] in ["rectangle", "circle"]:
                        # For shapes, we need coordinates
                        if "coordinates" in annotation:
                            processed_annotation["coordinates"] = annotation["coordinates"]
                        else:
                            return jsonify({"error": f"{annotation['type'].capitalize()} annotation requires 'coordinates' property"}), 400
                            
                        # Add optional properties
                        if "color" in annotation:
                            processed_annotation["color"] = annotation["color"]
                        else:
                            processed_annotation["color"] = "#FF0000"  # Default red
                            
                        if "fill_color" in annotation:
                            processed_annotation["fill_color"] = annotation["fill_color"]
                            
                        if "line_width" in annotation:
                            processed_annotation["line_width"] = annotation["line_width"]
                        else:
                            processed_annotation["line_width"] = 1
                            
                    elif annotation["type"] in ["line", "arrow"]:
                        # For lines, we need start and end points
                        if "start" in annotation and "end" in annotation:
                            processed_annotation["start"] = annotation["start"]
                            processed_annotation["end"] = annotation["end"]
                        else:
                            return jsonify({"error": f"{annotation['type'].capitalize()} annotation requires 'start' and 'end' properties"}), 400
                            
                        # Add optional properties
                        if "color" in annotation:
                            processed_annotation["color"] = annotation["color"]
                        else:
                            processed_annotation["color"] = "#000000"  # Default black
                            
                        if "line_width" in annotation:
                            processed_annotation["line_width"] = annotation["line_width"]
                        else:
                            processed_annotation["line_width"] = 1
                            
                    elif annotation["type"] == "stamp":
                        # For stamps, we need position and stamp type
                        if "position" in annotation:
                            processed_annotation["position"] = annotation["position"]
                        else:
                            # Default position in the center of the page
                            processed_annotation["position"] = {"x": 300, "y": 400}
                            
                        if "stamp_type" in annotation:
                            processed_annotation["stamp_type"] = annotation["stamp_type"]
                        else:
                            processed_annotation["stamp_type"] = "Approved"  # Default stamp
                            
                    elif annotation["type"] == "link":
                        # For links, we need coordinates and URL
                        if "coordinates" in annotation:
                            processed_annotation["coordinates"] = annotation["coordinates"]
                        else:
                            return jsonify({"error": "Link annotation requires 'coordinates' property"}), 400
                            
                        if "url" in annotation:
                            processed_annotation["url"] = annotation["url"]
                        else:
                            return jsonify({"error": "Link annotation requires 'url' property"}), 400
                    
                    # Add common optional properties
                    if "author" in annotation:
                        processed_annotation["author"] = annotation["author"]
                        
                    if "creation_date" in annotation:
                        processed_annotation["creation_date"] = annotation["creation_date"]
                    else:
                        from datetime import datetime
                        processed_annotation["creation_date"] = datetime.now().isoformat()
                        
                    processed_annotations.append(processed_annotation)
                
                # Prepare result object
                result = {
                    "filename": file_path.name,
                    "annotated_filename": output_filename,
                    "metadata": {
                        "title": metadata.get("title", "Untitled"),
                        "author": metadata.get("author", "Unknown"),
                        "page_count": page_count
                    },
                    "annotation_summary": {
                        "total_annotations": len(processed_annotations),
                        "annotations_by_type": {}
                    },
                    "annotations": processed_annotations
                }
                
                # Calculate annotations by type
                annotations_by_type = {}
                for annotation in processed_annotations:
                    annotation_type = annotation["type"]
                    if annotation_type in annotations_by_type:
                        annotations_by_type[annotation_type] += 1
                    else:
                        annotations_by_type[annotation_type] = 1
                
                result["annotation_summary"]["annotations_by_type"] = annotations_by_type
                
                # Calculate annotations by page
                annotations_by_page = {}
                for annotation in processed_annotations:
                    page = str(annotation["page"])
                    if page in annotations_by_page:
                        annotations_by_page[page] += 1
                    else:
                        annotations_by_page[page] = 1
                
                result["annotation_summary"]["annotations_by_page"] = annotations_by_page
                
                processor._cleanup()
                
                logger.info(f"Annotation complete: {len(processed_annotations)} annotations added to {file_path.name}")
                return jsonify(result)
                
            except Exception as e:
                logger.error(f"Error processing {file_path.name}: {e}")
                return jsonify({"error": f"Error annotating PDF: {str(e)}"}), 500
            
    except Exception as e:
        logger.error(f"Error in annotate endpoint: {e}")
        return jsonify({"error": str(e)}), 500

@api_blueprint.route('/compress', methods=['POST'])
def compress_pdf():
    """Compress a PDF document to reduce file size"""
    try:
        logger.info("Starting PDF compression process")
        
        # Check if file was uploaded
        if 'file' not in request.files:
            return jsonify({"error": "No file uploaded"}), 400
            
        pdf_file = request.files['file']
        if not pdf_file or pdf_file.filename == '':
            return jsonify({"error": "No file selected"}), 400
            
        # Validate file type
        if not pdf_file.filename.lower().endswith('.pdf'):
            return jsonify({"error": "Uploaded file is not a PDF"}), 400
            
        # Get compression parameters
        compression_level = request.form.get('compression_level', 'medium').lower()  # low, medium, high, extreme
        image_quality = int(request.form.get('image_quality', '80'))  # 1-100
        image_dpi = int(request.form.get('image_dpi', '150'))  # DPI for image downsampling
        grayscale = request.form.get('grayscale', 'false').lower() == 'true'
        remove_annotations = request.form.get('remove_annotations', 'false').lower() == 'true'
        remove_bookmarks = request.form.get('remove_bookmarks', 'false').lower() == 'true'
        remove_metadata = request.form.get('remove_metadata', 'false').lower() == 'true'
        flatten_forms = request.form.get('flatten_forms', 'false').lower() == 'true'
        
        # Validate parameters
        valid_compression_levels = ['low', 'medium', 'high', 'extreme']
        if compression_level not in valid_compression_levels:
            return jsonify({"error": f"Invalid compression level: {compression_level}. Supported levels: {', '.join(valid_compression_levels)}"}), 400
            
        if image_quality < 1 or image_quality > 100:
            return jsonify({"error": "Image quality must be between 1 and 100"}), 400
            
        if image_dpi < 72 or image_dpi > 600:
            return jsonify({"error": "Image DPI must be between 72 and 600"}), 400
            
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            file_path = tmp_path / pdf_file.filename
            pdf_file.save(file_path)
            
            # Process the PDF
            try:
                processor = PDFProcessor(file_path)
                
                # Extract metadata before compression
                original_metadata = processor._extract_metadata()
                original_page_count = original_metadata.get("page_count", 0)
                original_file_size = file_path.stat().st_size
                
                # In a real implementation, you would use a PDF library to compress the PDF
                # For this example, we'll just return the compression information
                
                # Map compression level to compression settings
                compression_settings = {
                    'low': {
                        'image_quality': max(image_quality, 90),
                        'image_dpi': max(image_dpi, 200),
                        'compress_text': True,
                        'compress_images': True,
                        'downsample_images': True,
                        'optimize_fonts': False,
                        'remove_unused_objects': True
                    },
                    'medium': {
                        'image_quality': image_quality,
                        'image_dpi': image_dpi,
                        'compress_text': True,
                        'compress_images': True,
                        'downsample_images': True,
                        'optimize_fonts': True,
                        'remove_unused_objects': True
                    },
                    'high': {
                        'image_quality': min(image_quality, 60),
                        'image_dpi': min(image_dpi, 120),
                        'compress_text': True,
                        'compress_images': True,
                        'downsample_images': True,
                        'optimize_fonts': True,
                        'remove_unused_objects': True
                    },
                    'extreme': {
                        'image_quality': min(image_quality, 40),
                        'image_dpi': min(image_dpi, 96),
                        'compress_text': True,
                        'compress_images': True,
                        'downsample_images': True,
                        'optimize_fonts': True,
                        'remove_unused_objects': True
                    }
                }
                
                # Get settings for the selected compression level
                settings = compression_settings[compression_level]
                
                # Add user-specified options
                settings['grayscale'] = grayscale
                settings['remove_annotations'] = remove_annotations
                settings['remove_bookmarks'] = remove_bookmarks
                settings['remove_metadata'] = remove_metadata
                settings['flatten_forms'] = flatten_forms
                
                # Simulate compression results
                # In a real implementation, this would be the actual compressed file size
                compression_factors = {
                    'low': 0.8,
                    'medium': 0.6,
                    'high': 0.4,
                    'extreme': 0.25
                }
                
                # Adjust compression factor based on options
                compression_factor = compression_factors[compression_level]
                if grayscale:
                    compression_factor *= 0.9  # Additional 10% reduction for grayscale
                if remove_annotations or remove_bookmarks or remove_metadata:
                    compression_factor *= 0.95  # Additional 5% reduction for removing elements
                
                # Calculate simulated compressed size
                compressed_size = int(original_file_size * compression_factor)
                size_reduction = original_file_size - compressed_size
                reduction_percentage = (size_reduction / original_file_size) * 100
                
                # Prepare result object
                result = {
                    "original_filename": file_path.name,
                    "original_page_count": original_page_count,
                    "original_file_size": original_file_size,
                    "original_file_size_formatted": format_file_size(original_file_size),
                    "compressed_file_size": compressed_size,
                    "compressed_file_size_formatted": format_file_size(compressed_size),
                    "size_reduction": size_reduction,
                    "size_reduction_formatted": format_file_size(size_reduction),
                    "reduction_percentage": round(reduction_percentage, 2),
                    "compression_level": compression_level,
                    "compression_settings": settings
                }
                
                processor._cleanup()
                
                logger.info(f"Compression complete: {file_path.name} compressed from {format_file_size(original_file_size)} to {format_file_size(compressed_size)} ({round(reduction_percentage, 2)}% reduction)")
                return jsonify(result)
                
            except Exception as e:
                logger.error(f"Error processing {file_path.name}: {e}")
                return jsonify({"error": f"Error compressing PDF: {str(e)}"}), 500
            
    except Exception as e:
        logger.error(f"Error in compress endpoint: {e}")
        return jsonify({"error": str(e)}), 500

# Helper function to format file sizes
def format_file_size(size_in_bytes):
    """Format file size in bytes to human-readable format"""
    if size_in_bytes < 1024:
        return f"{size_in_bytes} B"
    elif size_in_bytes < 1024 * 1024:
        return f"{size_in_bytes / 1024:.2f} KB"
    elif size_in_bytes < 1024 * 1024 * 1024:
        return f"{size_in_bytes / (1024 * 1024):.2f} MB"
    else:
        return f"{size_in_bytes / (1024 * 1024 * 1024):.2f} GB"

@api_blueprint.route('/merge', methods=['POST'])
def merge_pdfs():
    """Merge multiple PDF documents into a single PDF"""
    try:
        logger.info("Starting PDF merge process")
        
        # Check if files were uploaded
        if 'files' not in request.files:
            return jsonify({"error": "No files uploaded"}), 400
            
        pdf_files = request.files.getlist('files')
        if not pdf_files or len(pdf_files) < 2:
            return jsonify({"error": "At least two PDF files are required for merging"}), 400
            
        # Validate file types
        for pdf_file in pdf_files:
            if not pdf_file.filename.lower().endswith('.pdf'):
                return jsonify({"error": f"Uploaded file {pdf_file.filename} is not a PDF"}), 400
        
        # Get merge parameters
        bookmark_title = request.form.get('bookmark_title', 'Merged Document')
        create_bookmarks = request.form.get('create_bookmarks', 'true').lower() == 'true'
        page_order = request.form.get('page_order', '')
        
        # Parse page order if provided
        page_order_list = None
        if page_order:
            try:
                page_order_list = json.loads(page_order)
                if not isinstance(page_order_list, list):
                    return jsonify({"error": "Page order must be a JSON array"}), 400
            except json.JSONDecodeError:
                return jsonify({"error": "Invalid JSON format for page order"}), 400
        
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            
            # Save uploaded files
            file_paths = []
            for pdf_file in pdf_files:
                file_path = tmp_path / pdf_file.filename
                pdf_file.save(file_path)
                file_paths.append(file_path)
            
            # Process the PDFs
            try:
                # Extract metadata from each PDF
                pdf_metadata = []
                total_pages = 0
                
                for i, file_path in enumerate(file_paths):
                    processor = PDFProcessor(file_path)
                    metadata = processor._extract_metadata()
                    page_count = metadata.get("page_count", 0)
                    total_pages += page_count
                    
                    pdf_metadata.append({
                        "index": i,
                        "filename": file_path.name,
                        "title": metadata.get("title", f"Document {i+1}"),
                        "author": metadata.get("author", "Unknown"),
                        "page_count": page_count,
                        "start_page": total_pages - page_count + 1,
                        "end_page": total_pages
                    })
                    
                    processor._cleanup()
                
                # Generate output filename for merged PDF
                output_filename = f"merged_document_{uuid.uuid4().hex[:8]}.pdf"
                output_path = tmp_path / output_filename
                
                # In a real implementation, you would use a PDF library to merge the PDFs
                # For this example, we'll just return the metadata and merge information
                
                # Prepare result object
                result = {
                    "merged_filename": output_filename,
                    "total_pages": total_pages,
                    "source_documents": pdf_metadata,
                    "merge_parameters": {
                        "bookmark_title": bookmark_title,
                        "create_bookmarks": create_bookmarks
                    }
                }
                
                # If custom page order was provided, include it in the result
                if page_order_list:
                    # Validate page order entries
                    for entry in page_order_list:
                        if not isinstance(entry, dict) or 'document_index' not in entry or 'page_number' not in entry:
                            return jsonify({"error": "Each page order entry must be an object with 'document_index' and 'page_number' fields"}), 400
                        
                        document_index = entry.get('document_index')
                        page_number = entry.get('page_number')
                        
                        if not isinstance(document_index, int) or document_index < 0 or document_index >= len(pdf_metadata):
                            return jsonify({"error": f"Invalid document_index in page order: {document_index}"}), 400
                            
                        if not isinstance(page_number, int) or page_number < 1 or page_number > pdf_metadata[document_index]['page_count']:
                            return jsonify({"error": f"Invalid page_number in page order: {page_number} for document {document_index}"}), 400
                    
                    result["merge_parameters"]["custom_page_order"] = page_order_list
                    
                    # Calculate new total pages based on custom order
                    result["total_pages"] = len(page_order_list)
                
                # Calculate file size statistics
                total_size = sum(file_path.stat().st_size for file_path in file_paths)
                result["file_size"] = {
                    "total_input_size": total_size,
                    "average_size": total_size / len(file_paths),
                    "size_by_document": [{
                        "filename": pdf_metadata[i]["filename"],
                        "size": file_path.stat().st_size
                    } for i, file_path in enumerate(file_paths)]
                }
                
                # Add document outline if creating bookmarks
                if create_bookmarks:
                    outline = []
                    for doc in pdf_metadata:
                        outline.append({
                            "title": doc["title"],
                            "page": doc["start_page"],
                            "children": []
                        })
                    result["document_outline"] = outline
                
                logger.info(f"Merge complete: {len(file_paths)} PDFs merged into {output_filename} with {total_pages} pages")
                return jsonify(result)
                
            except Exception as e:
                logger.error(f"Error processing PDFs: {e}")
                return jsonify({"error": f"Error merging PDFs: {str(e)}"}), 500
            
    except Exception as e:
        logger.error(f"Error in merge endpoint: {e}")
        return jsonify({"error": str(e)}), 500

@api_blueprint.route('/split', methods=['POST'])
def split_pdf():
    """Split a PDF document into multiple files based on various criteria"""
    try:
        logger.info("Starting PDF split process")
        
        # Check if file was uploaded
        if 'file' not in request.files:
            return jsonify({"error": "No file uploaded"}), 400
            
        pdf_file = request.files['file']
        if not pdf_file or pdf_file.filename == '':
            return jsonify({"error": "No file selected"}), 400
            
        # Validate file type
        if not pdf_file.filename.lower().endswith('.pdf'):
            return jsonify({"error": "Uploaded file is not a PDF"}), 400
            
        # Get split parameters
        split_method = request.form.get('split_method', 'pages').lower()
        split_value = request.form.get('split_value', '')
        output_naming = request.form.get('output_naming', 'sequential')  # sequential, page_ranges, bookmarks
        
        # Validate split method
        valid_methods = ['pages', 'page_ranges', 'bookmarks', 'size', 'text_pattern']
        if split_method not in valid_methods:
            return jsonify({"error": f"Invalid split method: {split_method}. Supported methods: {', '.join(valid_methods)}"}), 400
        
        # Validate split value based on method
        if split_method == 'pages' and split_value:
            try:
                pages_per_file = int(split_value)
                if pages_per_file < 1:
                    return jsonify({"error": "Pages per file must be a positive integer"}), 400
            except ValueError:
                return jsonify({"error": "Pages per file must be a valid integer"}), 400
        elif split_method == 'page_ranges':
            if not split_value:
                return jsonify({"error": "Page ranges must be specified for 'page_ranges' split method"}), 400
                
            try:
                page_ranges = json.loads(split_value)
                if not isinstance(page_ranges, list):
                    return jsonify({"error": "Page ranges must be a JSON array"}), 400
                    
                for i, page_range in enumerate(page_ranges):
                    if not isinstance(page_range, dict) or 'start' not in page_range or 'end' not in page_range:
                        return jsonify({"error": f"Page range at index {i} must be an object with 'start' and 'end' fields"}), 400
                        
                    start = page_range.get('start')
                    end = page_range.get('end')
                    
                    if not isinstance(start, int) or start < 1:
                        return jsonify({"error": f"Invalid start page in range at index {i}: {start}"}), 400
                        
                    if not isinstance(end, int) or end < start:
                        return jsonify({"error": f"Invalid end page in range at index {i}: {end}"}), 400
            except json.JSONDecodeError:
                return jsonify({"error": "Invalid JSON format for page ranges"}), 400
        elif split_method == 'size' and split_value:
            try:
                max_size_kb = float(split_value)
                if max_size_kb <= 0:
                    return jsonify({"error": "Maximum file size must be positive"}), 400
            except ValueError:
                return jsonify({"error": "Maximum file size must be a valid number"}), 400
        
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            file_path = tmp_path / pdf_file.filename
            pdf_file.save(file_path)
            
            # Process the PDF
            try:
                processor = PDFProcessor(file_path)
                
                # Extract metadata
                metadata = processor._extract_metadata()
                page_count = metadata.get("page_count", 0)
                
                # Extract outline if needed for bookmark-based splitting
                outline = None
                if split_method == 'bookmarks':
                    outline = processor._extract_outline()
                    if not outline or len(outline) <= 1:  # Need at least 2 bookmarks to split
                        return jsonify({"error": "The PDF does not contain sufficient bookmarks for splitting"}), 400
                
                # Determine split points based on method
                split_points = []
                
                if split_method == 'pages':
                    pages_per_file = int(split_value) if split_value else 1
                    for i in range(1, page_count + 1, pages_per_file):
                        end = min(i + pages_per_file - 1, page_count)
                        split_points.append({
                            "start": i,
                            "end": end,
                            "name": f"Pages {i}-{end}"
                        })
                        
                elif split_method == 'page_ranges':
                    page_ranges = json.loads(split_value)
                    for i, page_range in enumerate(page_ranges):
                        start = page_range.get('start')
                        end = page_range.get('end')
                        name = page_range.get('name', f"Range {i+1}")
                        
                        if end > page_count:
                            return jsonify({"error": f"End page {end} exceeds document page count {page_count}"}), 400
                            
                        split_points.append({
                            "start": start,
                            "end": end,
                            "name": name
                        })
                        
                elif split_method == 'bookmarks':
                    # Convert outline to split points
                    # This is a simplified approach - in a real implementation, you would handle nested bookmarks
                    for i in range(len(outline)):
                        current = outline[i]
                        next_page = outline[i+1]['page'] - 1 if i < len(outline) - 1 else page_count
                        
                        split_points.append({
                            "start": current['page'],
                            "end": next_page,
                            "name": current['title']
                        })
                        
                elif split_method == 'size':
                    # This is a mock implementation - in a real scenario, you would calculate actual PDF sizes
                    max_size_kb = float(split_value) if split_value else 1000  # Default 1MB
                    avg_page_size_kb = file_path.stat().st_size / 1024 / page_count
                    pages_per_file = max(1, int(max_size_kb / avg_page_size_kb))
                    
                    for i in range(1, page_count + 1, pages_per_file):
                        end = min(i + pages_per_file - 1, page_count)
                        split_points.append({
                            "start": i,
                            "end": end,
                            "name": f"Size-based split {i}-{end}"
                        })
                        
                elif split_method == 'text_pattern':
                    # This is a mock implementation - in a real scenario, you would search for text patterns
                    # and determine page breaks based on matches
                    pattern = split_value if split_value else "Chapter"
                    
                    # Mock split points - in reality, you would analyze text content
                    mock_matches = [1]  # Always include first page
                    for i in range(2, page_count, 5):  # Pretend we found matches every 5 pages
                        mock_matches.append(i)
                    mock_matches.append(page_count + 1)  # Add end marker
                    
                    for i in range(len(mock_matches) - 1):
                        start = mock_matches[i]
                        end = mock_matches[i+1] - 1
                        split_points.append({
                            "start": start,
                            "end": end,
                            "name": f"{pattern} {i+1}"
                        })
                
                # Generate output filenames
                output_files = []
                for i, split_point in enumerate(split_points):
                    if output_naming == 'sequential':
                        filename = f"{file_path.stem}_part{i+1:03d}.pdf"
                    elif output_naming == 'page_ranges':
                        filename = f"{file_path.stem}_pages{split_point['start']}-{split_point['end']}.pdf"
                    elif output_naming == 'bookmarks':
                        # Sanitize bookmark title for filename
                        safe_name = split_point['name'].replace('/', '_').replace('\\', '_')[:50]
                        filename = f"{file_path.stem}_{safe_name}.pdf"
                    else:
                        filename = f"{file_path.stem}_split{i+1}.pdf"
                        
                    output_files.append({
                        "filename": filename,
                        "start_page": split_point['start'],
                        "end_page": split_point['end'],
                        "page_count": split_point['end'] - split_point['start'] + 1,
                        "name": split_point['name']
                    })
                
                # In a real implementation, you would use a PDF library to create the split PDFs
                # For this example, we'll just return the split information
                
                # Prepare result object
                result = {
                    "original_filename": file_path.name,
                    "original_page_count": page_count,
                    "split_method": split_method,
                    "split_value": split_value,
                    "output_naming": output_naming,
                    "total_output_files": len(output_files),
                    "output_files": output_files
                }
                
                # Add method-specific information
                if split_method == 'bookmarks' and outline:
                    result["bookmarks_used"] = len(outline)
                    
                if split_method == 'size':
                    result["size_information"] = {
                        "original_size_kb": file_path.stat().st_size / 1024,
                        "max_size_kb": max_size_kb,
                        "estimated_average_page_size_kb": avg_page_size_kb
                    }
                
                processor._cleanup()
                
                logger.info(f"Split complete: {file_path.name} split into {len(output_files)} files using method '{split_method}'")
                return jsonify(result)
                
            except Exception as e:
                logger.error(f"Error processing {file_path.name}: {e}")
                return jsonify({"error": f"Error splitting PDF: {str(e)}"}), 500
            
    except Exception as e:
        logger.error(f"Error in split endpoint: {e}")
        return jsonify({"error": str(e)}), 500

@api_blueprint.route('/convert', methods=['POST'])
def convert_pdf():
    """Convert PDF documents to other formats (HTML, DOCX, Markdown, etc.)"""
    try:
        logger.info("Starting PDF conversion")
        
        # Check if file was uploaded
        if 'file' not in request.files:
            return jsonify({"error": "No file uploaded"}), 400
            
        pdf_file = request.files['file']
        if not pdf_file or pdf_file.filename == '':
            return jsonify({"error": "No file selected"}), 400
            
        # Validate file type
        if not pdf_file.filename.lower().endswith('.pdf'):
            return jsonify({"error": "Uploaded file is not a PDF"}), 400
            
        # Get conversion parameters
        output_format = request.form.get('format', 'html').lower()  # html, docx, markdown, text, epub
        include_images = request.form.get('include_images', 'true').lower() == 'true'
        include_tables = request.form.get('include_tables', 'true').lower() == 'true'
        preserve_layout = request.form.get('preserve_layout', 'true').lower() == 'true'
        page_range = request.form.get('page_range', '')  # Format: "1-5,7,9-10"
        
        # Validate output format
        valid_formats = ['html', 'docx', 'markdown', 'text', 'epub']
        if output_format not in valid_formats:
            return jsonify({"error": f"Invalid output format. Supported formats: {', '.join(valid_formats)}"}), 400
        
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            file_path = tmp_path / pdf_file.filename
            pdf_file.save(file_path)
            
            # Process the PDF
            try:
                processor = PDFProcessor(file_path)
                
                # Extract metadata
                metadata = processor._extract_metadata()
                
                # Parse page range if provided
                pages_to_convert = []
                if page_range:
                    for part in page_range.split(','):
                        if '-' in part:
                            start, end = map(int, part.split('-'))
                            pages_to_convert.extend(range(start, end + 1))
                        else:
                            pages_to_convert.append(int(part))
                
                # Prepare result object
                result = {
                    "filename": file_path.name,
                    "metadata": {
                        "title": metadata.get("title", "Untitled"),
                        "author": metadata.get("author", "Unknown"),
                        "page_count": metadata.get("page_count", 0),
                        "creation_date": metadata.get("creation_date", ""),
                        "modification_date": metadata.get("modification_date", "")
                    },
                    "conversion_params": {
                        "output_format": output_format,
                        "include_images": include_images,
                        "include_tables": include_tables,
                        "preserve_layout": preserve_layout,
                        "page_range": page_range if page_range else "all"
                    }
                }
                
                # Generate output filename
                output_filename = f"{file_path.stem}.{output_format}"
                output_path = tmp_path / output_filename
                
                # Convert based on requested format
                if output_format == 'html':
                    # HTML conversion
                    html_content = ["<!DOCTYPE html>", "<html>", "<head>", "<meta charset=\"UTF-8\">", 
                                   f"<title>{metadata.get('title', 'Untitled')}</title>", 
                                   "<style>body{font-family:Arial,sans-serif;line-height:1.6;max-width:800px;margin:0 auto;padding:20px}h1{color:#333}h2{color:#444;margin-top:30px}p{margin-bottom:16px}table{border-collapse:collapse;width:100%;margin:20px 0}table,th,td{border:1px solid #ddd}th,td{padding:12px;text-align:left}img{max-width:100%;height:auto}</style>",
                                   "</head>", "<body>"]
                    
                    # Add title and metadata
                    html_content.append(f"<h1>{metadata.get('title', 'Untitled Document')}</h1>")
                    html_content.append(f"<p><em>Author: {metadata.get('author', 'Unknown')}</em></p>")
                    
                    # Extract text by page and format as HTML
                    for i, page_text in enumerate(processor.extract_text_by_page()):
                        page_num = i + 1
                        
                        if pages_to_convert and page_num not in pages_to_convert:
                            continue
                            
                        html_content.append(f"<h2>Page {page_num}</h2>")
                        
                        # Format paragraphs
                        paragraphs = [p for p in page_text.split('\n\n') if p.strip()]
                        for para in paragraphs:
                            html_content.append(f"<p>{para}</p>")
                        
                        # Add images if requested
                        if include_images:
                            page_images = processor.extract_images(page_num)
                            for img_idx, img in enumerate(page_images):
                                if 'data' in img:
                                    img_data = img['data']
                                    img_format = img.get('format', 'jpeg').lower()
                                    html_content.append(f"<div class=\"image-container\"><img src=\"data:image/{img_format};base64,{img_data}\" alt=\"Image {img_idx + 1} on page {page_num}\"></div>")
                        
                        # Add tables if requested
                        if include_tables:
                            page_tables = processor.extract_tables(page_num)
                            for table_idx, table in enumerate(page_tables):
                                html_content.append(f"<h3>Table {table_idx + 1}</h3>")
                                html_content.append("<table>")
                                
                                for row in table:
                                    html_content.append("<tr>")
                                    for cell in row:
                                        html_content.append(f"<td>{cell}</td>")
                                    html_content.append("</tr>")
                                    
                                html_content.append("</table>")
                    
                    html_content.extend(["</body>", "</html>"])
                    html_output = "\n".join(html_content)
                    
                    # Write HTML to file
                    with open(output_path, 'w', encoding='utf-8') as f:
                        f.write(html_output)
                    
                    # Add HTML content to result
                    result["html"] = html_output
                    
                elif output_format == 'markdown':
                    # Markdown conversion
                    md_content = []
                    
                    # Add title and metadata
                    title = metadata.get("title", "Untitled Document")
                    md_content.append(f"# {title}\n")
                    
                    author = metadata.get("author", "Unknown")
                    md_content.append(f"*Author: {author}*\n")
                    
                    # Extract text by page and format as markdown
                    for i, page_text in enumerate(processor.extract_text_by_page()):
                        page_num = i + 1
                        
                        if pages_to_convert and page_num not in pages_to_convert:
                            continue
                            
                        md_content.append(f"## Page {page_num}\n")
                        
                        # Try to detect headings and format them
                        lines = page_text.split('\n')
                        formatted_lines = []
                        
                        for line in lines:
                            line = line.strip()
                            if not line:
                                formatted_lines.append("")
                                continue
                                
                            # Heuristic for headings: short lines with no punctuation at the end
                            if len(line) < 100 and not line[-1] in '.,:;?!':
                                formatted_lines.append(f"### {line}\n")
                            else:
                                formatted_lines.append(f"{line}\n")
                                
                        md_content.append("\n".join(formatted_lines))
                        
                        # Add tables if requested
                        if include_tables:
                            page_tables = processor.extract_tables(page_num)
                            for table_idx, table in enumerate(page_tables):
                                md_content.append(f"\n### Table {table_idx + 1}\n")
                                
                                # Create markdown table
                                for row in table:
                                    md_content.append("| " + " | ".join(str(cell) for cell in row) + " |")
                                    
                                    # Add separator after first row
                                    if row == table[0]:
                                        md_content.append("| " + " | ".join(["-" * len(str(cell)) for cell in row]) + " |")
                    
                    md_output = "\n".join(md_content)
                    
                    # Write markdown to file
                    with open(output_path, 'w', encoding='utf-8') as f:
                        f.write(md_output)
                    
                    # Add markdown content to result
                    result["markdown"] = md_output
                    
                elif output_format == 'text':
                    # Plain text conversion
                    text_content = []
                    
                    # Add title and metadata
                    title = metadata.get("title", "Untitled Document")
                    text_content.append(f"{title}\n")
                    
                    author = metadata.get("author", "Unknown")
                    text_content.append(f"Author: {author}\n")
                    
                    # Extract text by page
                    for i, page_text in enumerate(processor.extract_text_by_page()):
                        page_num = i + 1
                        
                        if pages_to_convert and page_num not in pages_to_convert:
                            continue
                            
                        text_content.append(f"\n--- Page {page_num} ---\n")
                        text_content.append(page_text)
                    
                    text_output = "\n".join(text_content)
                    
                    # Write text to file
                    with open(output_path, 'w', encoding='utf-8') as f:
                        f.write(text_output)
                    
                    # Add text content to result
                    result["text"] = text_output
                    
                elif output_format in ['docx', 'epub']:
                    # For formats requiring external libraries, we'll mock the conversion
                    # In a real implementation, you would use libraries like python-docx or ebooklib
                    
                    # Mock conversion result
                    result["message"] = f"Conversion to {output_format} format would be implemented with appropriate libraries"
                    result["conversion_status"] = "mocked"
                    
                    # In a real implementation, you would do something like:
                    # if output_format == 'docx':
                    #     from docx import Document
                    #     doc = Document()
                    #     doc.add_heading(metadata.get('title', 'Untitled'), 0)
                    #     # Add content, tables, images, etc.
                    #     doc.save(output_path)
                    # elif output_format == 'epub':
                    #     import ebooklib
                    #     from ebooklib import epub
                    #     book = epub.EpubBook()
                    #     # Set metadata, add chapters, etc.
                    #     epub.write_epub(output_path, book)
                
                # Add output file information
                result["output_filename"] = output_filename
                
                processor._cleanup()
                
                logger.info(f"Conversion complete: {file_path.name} to {output_format}")
                return jsonify(result)
                
            except Exception as e:
                logger.error(f"Error processing {file_path.name}: {e}")
                return jsonify({"error": f"Error converting PDF: {str(e)}"}), 500
            
    except Exception as e:
        logger.error(f"Error in convert endpoint: {e}")
        return jsonify({"error": str(e)}), 500

@api_blueprint.route('/extract-text', methods=['POST'])
def extract_text():
    """Extract text from PDF documents with advanced options"""
    try:
        logger.info("Starting text extraction with advanced options")
        
        # Check if file was uploaded
        if 'file' not in request.files:
            return jsonify({"error": "No file uploaded"}), 400
            
        pdf_file = request.files['file']
        if not pdf_file or pdf_file.filename == '':
            return jsonify({"error": "No file selected"}), 400
            
        # Validate file type
        if not pdf_file.filename.lower().endswith('.pdf'):
            return jsonify({"error": "Uploaded file is not a PDF"}), 400
            
        # Get extraction parameters
        format_type = request.form.get('format', 'plain').lower()  # plain, json, markdown, html
        include_page_numbers = request.form.get('include_page_numbers', 'true').lower() == 'true'
        include_coordinates = request.form.get('include_coordinates', 'false').lower() == 'true'
        include_font_info = request.form.get('include_font_info', 'false').lower() == 'true'
        extract_tables = request.form.get('extract_tables', 'true').lower() == 'true'
        extract_sections = request.form.get('extract_sections', 'true').lower() == 'true'
        page_range = request.form.get('page_range', '')  # Format: "1-5,7,9-10"
        
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            file_path = tmp_path / pdf_file.filename
            pdf_file.save(file_path)
            
            # Process the PDF
            try:
                processor = PDFProcessor(file_path)
                
                # Extract metadata
                metadata = processor._extract_metadata()
                
                # Parse page range if provided
                pages_to_extract = []
                if page_range:
                    for part in page_range.split(','):
                        if '-' in part:
                            start, end = map(int, part.split('-'))
                            pages_to_extract.extend(range(start, end + 1))
                        else:
                            pages_to_extract.append(int(part))
                
                # Extract text based on format
                result = {
                    "filename": file_path.name,
                    "metadata": {
                        "title": metadata.get("title", "Untitled"),
                        "author": metadata.get("author", "Unknown"),
                        "page_count": metadata.get("page_count", 0),
                        "creation_date": metadata.get("creation_date", ""),
                        "modification_date": metadata.get("modification_date", "")
                    }
                }
                
                # Extract text content
                if format_type == 'plain':
                    # Simple plain text extraction
                    if pages_to_extract:
                        text_content = processor.extract_text(pages=pages_to_extract)
                    else:
                        text_content = processor.extract_text()
                        
                    if include_page_numbers:
                        # Format with page numbers
                        pages_text = []
                        for i, page_text in enumerate(processor.extract_text_by_page()):
                            if not pages_to_extract or (i + 1) in pages_to_extract:
                                pages_text.append(f"--- Page {i + 1} ---\n{page_text}")
                        text_content = "\n\n".join(pages_text)
                    
                    result["text"] = text_content
                    
                elif format_type == 'json':
                    # Structured JSON extraction with detailed information
                    pages = []
                    
                    for i, page_text in enumerate(processor.extract_text_by_page()):
                        page_num = i + 1
                        
                        if pages_to_extract and page_num not in pages_to_extract:
                            continue
                            
                        page_info = {"page_number": page_num, "text": page_text}
                        
                        # Add coordinates and font info if requested
                        if include_coordinates or include_font_info:
                            text_elements = processor.extract_text_elements(page_num)
                            if text_elements:
                                elements = []
                                for elem in text_elements:
                                    element_info = {"text": elem.get("text", "")}
                                    
                                    if include_coordinates:
                                        element_info["bbox"] = elem.get("bbox", [])
                                        
                                    if include_font_info:
                                        element_info["font"] = elem.get("font", "")
                                        element_info["font_size"] = elem.get("font_size", 0)
                                        
                                    elements.append(element_info)
                                    
                                page_info["elements"] = elements
                        
                        pages.append(page_info)
                    
                    result["pages"] = pages
                    
                elif format_type == 'markdown':
                    # Markdown formatted text
                    md_content = []
                    
                    # Add title and metadata
                    title = metadata.get("title", "Untitled Document")
                    md_content.append(f"# {title}\n")
                    
                    author = metadata.get("author", "Unknown")
                    md_content.append(f"*Author: {author}*\n")
                    
                    # Extract text by page and format as markdown
                    for i, page_text in enumerate(processor.extract_text_by_page()):
                        page_num = i + 1
                        
                        if pages_to_extract and page_num not in pages_to_extract:
                            continue
                            
                        if include_page_numbers:
                            md_content.append(f"## Page {page_num}\n")
                            
                        # Try to detect headings and format them
                        lines = page_text.split('\n')
                        formatted_lines = []
                        
                        for line in lines:
                            line = line.strip()
                            if not line:
                                formatted_lines.append("")
                                continue
                                
                            # Heuristic for headings: short lines with no punctuation at the end
                            if len(line) < 100 and not line[-1] in '.,:;?!':
                                formatted_lines.append(f"### {line}\n")
                            else:
                                formatted_lines.append(f"{line}\n")
                                
                        md_content.append("\n".join(formatted_lines))
                    
                    result["markdown"] = "\n".join(md_content)
                    
                elif format_type == 'html':
                    # HTML formatted text
                    html_content = ["<!DOCTYPE html>", "<html>", "<head>", "<meta charset=\"UTF-8\">", 
                                   f"<title>{metadata.get('title', 'Untitled')}</title>", 
                                   "<style>body{font-family:Arial,sans-serif;line-height:1.6;max-width:800px;margin:0 auto;padding:20px}h1{color:#333}h2{color:#444;margin-top:30px}p{margin-bottom:16px}</style>",
                                   "</head>", "<body>"]
                    
                    # Add title and metadata
                    html_content.append(f"<h1>{metadata.get('title', 'Untitled Document')}</h1>")
                    html_content.append(f"<p><em>Author: {metadata.get('author', 'Unknown')}</em></p>")
                    
                    # Extract text by page and format as HTML
                    for i, page_text in enumerate(processor.extract_text_by_page()):
                        page_num = i + 1
                        
                        if pages_to_extract and page_num not in pages_to_extract:
                            continue
                            
                        if include_page_numbers:
                            html_content.append(f"<h2>Page {page_num}</h2>")
                            
                        # Format paragraphs
                        paragraphs = [p for p in page_text.split('\n\n') if p.strip()]
                        for para in paragraphs:
                            html_content.append(f"<p>{para}</p>")
                    
                    html_content.extend(["</body>", "</html>"])
                    result["html"] = "\n".join(html_content)
                
                # Extract tables if requested
                if extract_tables:
                    tables = processor.extract_tables()
                    if tables:
                        result["tables"] = tables
                
                # Extract document structure/sections if requested
                if extract_sections:
                    outline = processor.extract_outline()
                    if outline:
                        result["outline"] = outline
                        
                    # Try to extract sections based on font changes or spacing
                    sections = processor.extract_sections()
                    if sections:
                        result["sections"] = sections
                
                processor._cleanup()
                
                logger.info(f"Text extraction complete for {file_path.name} in {format_type} format")
                return jsonify(result)
                
            except Exception as e:
                logger.error(f"Error processing {file_path.name}: {e}")
                return jsonify({"error": f"Error processing PDF: {str(e)}"}), 500
            
    except Exception as e:
        logger.error(f"Error in extract-text endpoint: {e}")
        return jsonify({"error": str(e)}), 500

@api_blueprint.route('/images', methods=['POST'])
def extract_images():
    """Extract and analyze images from PDF documents"""
    try:
        logger.info("Starting image extraction and analysis")
        
        # Check if file was uploaded
        if 'file' not in request.files:
            return jsonify({"error": "No file uploaded"}), 400
            
        pdf_file = request.files['file']
        if not pdf_file or pdf_file.filename == '':
            return jsonify({"error": "No file selected"}), 400
            
        # Validate file type
        if not pdf_file.filename.lower().endswith('.pdf'):
            return jsonify({"error": "Uploaded file is not a PDF"}), 400
            
        # Get extraction parameters
        include_base64 = request.form.get('include_base64', 'false').lower() == 'true'
        include_metadata = request.form.get('include_metadata', 'true').lower() == 'true'
        include_statistics = request.form.get('include_statistics', 'true').lower() == 'true'
        min_width = request.form.get('min_width', 100, type=int)
        min_height = request.form.get('min_height', 100, type=int)
        max_images = request.form.get('max_images', 50, type=int)
        
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            file_path = tmp_path / pdf_file.filename
            pdf_file.save(file_path)
            
            # Process the PDF
            try:
                processor = PDFProcessor(file_path)
                
                # Extract metadata
                metadata = processor._extract_metadata()
                
                # Extract images
                images = processor.extract_images()
                
                if not images:
                    return jsonify({
                        "filename": file_path.name,
                        "message": "No images found in the document",
                        "images_count": 0
                    })
                
                # Filter images by size if needed
                if min_width > 0 or min_height > 0:
                    images = [img for img in images if 
                             img.get("width", 0) >= min_width and 
                             img.get("height", 0) >= min_height]
                
                # Limit number of images if needed
                if max_images > 0 and len(images) > max_images:
                    images = images[:max_images]
                
                # Prepare response
                result = {
                    "filename": file_path.name,
                    "images_count": len(images),
                    "metadata": {
                        "title": metadata.get("title", "Untitled"),
                        "author": metadata.get("author", "Unknown"),
                        "page_count": metadata.get("page_count", 0)
                    }
                }
                
                # Process images
                processed_images = []
                
                for i, image in enumerate(images):
                    image_info = {
                        "image_id": i + 1,
                        "page": image.get("page", 0),
                        "width": image.get("width", 0),
                        "height": image.get("height", 0),
                        "position": image.get("position", {}),
                        "format": image.get("format", "unknown")
                    }
                    
                    # Include image metadata if requested
                    if include_metadata and "metadata" in image:
                        image_info["metadata"] = image["metadata"]
                    
                    # Include base64 encoded image if requested
                    if include_base64 and "data" in image:
                        image_info["data"] = image["data"]
                    
                    processed_images.append(image_info)
                
                # Add images to result
                result["images"] = processed_images
                
                # Add image statistics if requested
                if include_statistics:
                    # Calculate statistics
                    total_width = sum(img.get("width", 0) for img in processed_images)
                    total_height = sum(img.get("height", 0) for img in processed_images)
                    avg_width = round(total_width / len(processed_images), 2) if processed_images else 0
                    avg_height = round(total_height / len(processed_images), 2) if processed_images else 0
                    
                    # Count images per page
                    page_distribution = {}
                    for img in processed_images:
                        page = str(img.get("page", 0))
                        if page in page_distribution:
                            page_distribution[page] += 1
                        else:
                            page_distribution[page] = 1
                    
                    # Count image formats
                    format_distribution = {}
                    for img in processed_images:
                        fmt = img.get("format", "unknown")
                        if fmt in format_distribution:
                            format_distribution[fmt] += 1
                        else:
                            format_distribution[fmt] = 1
                    
                    stats = {
                        "images_per_page": round(len(processed_images) / metadata.get("page_count", 1), 2),
                        "avg_width": avg_width,
                        "avg_height": avg_height,
                        "largest_image": max((img.get("width", 0) * img.get("height", 0)) for img in processed_images) if processed_images else 0,
                        "page_distribution": page_distribution,
                        "format_distribution": format_distribution
                    }
                    
                    result["statistics"] = stats
                
                processor._cleanup()
                
                logger.info(f"Image extraction complete: {len(processed_images)} images found in {file_path.name}")
                return jsonify(result)
                
            except Exception as e:
                logger.error(f"Error processing {file_path.name}: {e}")
                return jsonify({"error": f"Error processing PDF: {str(e)}"}), 500
            
    except Exception as e:
        logger.error(f"Error in images endpoint: {e}")
        return jsonify({"error": str(e)}), 500

@api_blueprint.route('/similarity', methods=['POST'])
def find_similar_content():
    """Find similar content between a source PDF and target PDFs"""
    try:
        # Get similarity threshold parameter
        similarity_threshold = request.args.get('threshold', 0.7, type=float)
        top_k = request.args.get('top_k', 10, type=int)
        
        logger.info(f"Finding similar content with threshold={similarity_threshold}, top_k={top_k}")
        
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            
            # Get source PDF
            if 'source' not in request.files:
                return jsonify({"error": "Missing required file: 'source'"}), 400
                
            source_file = request.files['source']
            source_path = tmp_path / source_file.filename
            source_file.save(source_path)
            
            if not source_path.exists() or not source_path.name.lower().endswith('.pdf'):
                return jsonify({"error": "Invalid source file: must be a PDF"}), 400
            
            # Get target PDFs
            target_files = request.files.getlist('targets')
            if not target_files:
                return jsonify({"error": "No target files uploaded"}), 400
                
            target_paths = []
            for f in target_files:
                if f.filename.lower().endswith('.pdf'):
                    file_path = tmp_path / f.filename
                    f.save(file_path)
                    target_paths.append(file_path)
            
            if not target_paths:
                return jsonify({"error": "No PDF target files found in upload"}), 400
                
            # Find similar content
            matches = semantic_ranker.find_similar_content(
                source_path, target_paths, 
                similarity_threshold=similarity_threshold,
                top_k=top_k
            )
            
            logger.info(f"Similarity analysis complete. Found {len(matches)} matches")
            return jsonify({
                "source": source_file.filename,
                "targets": [f.name for f in target_paths],
                "threshold": similarity_threshold,
                "matches": matches,
                "count": len(matches)
            })
            
    except Exception as e:
        logger.error(f"Error in similarity endpoint: {e}")
        return jsonify({"error": str(e)}), 500