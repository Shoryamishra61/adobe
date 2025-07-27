from sentence_transformers import SentenceTransformer, util
import torch
import json
import fitz
import re
import os
import numpy as np
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional, Union
from concurrent.futures import ThreadPoolExecutor

from ..config.config import (
    SENTENCE_TRANSFORMER_MODEL,
    ENABLE_CACHING,
    MAX_WORKERS,
    BATCH_SIZE
)
from ..utils.cache import cached
from ..utils.logging_config import get_logger
from ..utils.text_processing import clean_text, extract_keywords, chunk_text

# Initialize logger
logger = get_logger(__name__)

class SemanticRanker:
    """A class for semantic ranking of PDF documents based on query relevance.
    
    This class uses sentence transformers to embed text and perform semantic search
    across PDF documents, ranking content by relevance to a query.
    """
    
    def __init__(self, model_name: str = None, device: str = None):
        """Initialize the SemanticRanker with a sentence transformer model.
        
        Args:
            model_name: Name of the sentence transformer model to use
            device: Device to run the model on ('cpu' or 'cuda')
        """
        self.model_name = model_name or SENTENCE_TRANSFORMER_MODEL
        
        # Auto-detect device if not specified
        if device is None:
            device = 'cuda' if torch.cuda.is_available() else 'cpu'
        
        logger.info(f"Initializing SemanticRanker with model {self.model_name} on {device}")
        try:
            self.model = SentenceTransformer(self.model_name, device=device)
            self.device = device
            logger.info(f"Successfully loaded model {self.model_name}")
        except Exception as e:
            logger.error(f"Failed to load model {self.model_name}: {e}")
            # Fallback to a simpler model on CPU if loading fails
            self.model_name = 'all-MiniLM-L6-v2'
            self.model = SentenceTransformer(self.model_name, device='cpu')
            self.device = 'cpu'
            logger.warning(f"Falling back to {self.model_name} on CPU")

    @cached
    def _embed(self, texts: Union[str, List[str]], batch_size: int = None) -> torch.Tensor:
        """Embed text using the sentence transformer model.
        
        Args:
            texts: Text or list of texts to embed
            batch_size: Batch size for embedding (defaults to config.BATCH_SIZE)
            
        Returns:
            Tensor of embeddings
        """
        if batch_size is None:
            batch_size = BATCH_SIZE
            
        logger.debug(f"Embedding {len(texts) if isinstance(texts, list) else 1} texts")
        try:
            return self.model.encode(
                texts, 
                convert_to_tensor=True, 
                batch_size=batch_size,
                show_progress_bar=False
            )
        except Exception as e:
            logger.error(f"Error during embedding: {e}")
            # Return empty tensor as fallback
            if isinstance(texts, list):
                return torch.zeros((len(texts), self.model.get_sentence_embedding_dimension()))
            return torch.zeros(self.model.get_sentence_embedding_dimension())

    @cached
    def _get_rich_blocks(self, pdf_path: Union[str, Path]) -> List[Tuple[str, int, Optional[str]]]:
        """Extract rich text blocks from a PDF document.
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            List of tuples containing (text, page_number, section_title)
        """
        pdf_path = Path(pdf_path)
        logger.info(f"Extracting rich text blocks from {pdf_path.name}")
        
        blocks = []
        section_title = None
        
        try:
            doc = fitz.open(pdf_path)
            
            # First pass: extract section titles (headings)
            headings = {}
            for pno, page in enumerate(doc, 1):
                for block in page.get_text("dict")["blocks"]:
                    if block['type'] == 0:  # Text block
                        # Check if this is a heading (larger font or bold)
                        is_heading = False
                        for line in block['lines']:
                            for span in line['spans']:
                                if span.get('flags', 0) & 16 > 0 or span.get('size', 0) > 12:  # Bold or large font
                                    text = span['text'].strip()
                                    if text and len(text) < 100:  # Reasonable heading length
                                        headings[pno] = text
                                        is_heading = True
                                        break
                            if is_heading:
                                break
            
            # Second pass: extract content blocks with section context
            for pno, page in enumerate(doc, 1):
                # Get current section title
                current_section = headings.get(pno, section_title)
                
                for block in page.get_text("dict")["blocks"]:
                    if block['type'] == 0:  # Text block
                        # Extract and clean text
                        text = ' '.join(span['text'] for line in block['lines'] for span in line['spans'])
                        text = clean_text(text)
                        
                        # Only keep substantial blocks
                        if len(text) > 50:  # Minimum length for meaningful content
                            blocks.append((text, pno, current_section))
                
                # Remember section for next page if no new heading is found
                section_title = current_section
                
            doc.close()
            logger.info(f"Extracted {len(blocks)} rich text blocks from {pdf_path.name}")
            
        except Exception as e:
            logger.error(f"Error extracting rich blocks from {pdf_path.name}: {e}")
            
        return blocks

    @cached
    def rank(self, collection_json: Union[str, Path], base_path: Union[str, Path], 
             top_k: int = 5) -> List[Dict[str, Any]]:
        """Rank PDF documents based on relevance to a query defined in a collection JSON.
        
        Args:
            collection_json: Path to the collection JSON file
            base_path: Base path for PDF files
            top_k: Number of top results to return
            
        Returns:
            List of dictionaries containing ranked results
        """
        collection_json = Path(collection_json)
        base_path = Path(base_path)
        logger.info(f"Ranking documents based on collection {collection_json.name}")
        
        try:
            # Load collection configuration
            with open(collection_json, 'r', encoding='utf8') as f:
                cfg = json.load(f)

            # Construct query from persona and task
            query = f"{cfg['persona']['role']} : {cfg['job_to_be_done']['task']}"
            logger.info(f"Query: {query}")
            
            # Embed query
            query_vector = self._embed(query)

            # Process documents in parallel
            corpus = []
            metadata = []
            
            def process_document(doc_info):
                doc_results = []
                try:
                    pdf_path = base_path / 'PDFs' / doc_info['filename']
                    if not pdf_path.exists():
                        logger.warning(f"PDF file not found: {pdf_path}")
                        return []
                        
                    # Extract rich text blocks with section titles
                    for txt, pno, section in self._get_rich_blocks(pdf_path):
                        doc_results.append({
                            "doc": doc_info['filename'],
                            "page": pno,
                            "text": txt,
                            "section": section or "Unknown section",
                            "preview": txt[:90] + "..."
                        })
                except Exception as e:
                    logger.error(f"Error processing document {doc_info['filename']}: {e}")
                return doc_results
            
            # Process documents in parallel
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                all_results = list(executor.map(process_document, cfg['documents']))
            
            # Flatten results
            for doc_results in all_results:
                for result in doc_results:
                    metadata.append(result)
                    corpus.append(result["text"])
            
            if not corpus:
                logger.warning("No text extracted from documents")
                return []
                
            # Embed corpus and calculate similarity scores
            logger.info(f"Embedding corpus of {len(corpus)} text blocks")
            corpus_vectors = self._embed(corpus, batch_size=BATCH_SIZE)
            scores = util.cos_sim(query_vector, corpus_vectors)[0]

            # Get top results
            k = min(top_k, len(corpus))
            top_results = torch.topk(scores, k)
            
            # Format results
            results = [
                {
                    "document": metadata[i]["doc"],
                    "page": metadata[i]["page"],
                    "section_title": metadata[i]["section"],
                    "preview": metadata[i]["preview"],
                    "importance_rank": r + 1,
                    "score": round(float(top_results.values[r]), 4)
                }
                for r, i in enumerate(top_results.indices)
            ]
            
            logger.info(f"Ranked {len(results)} results for query")
            return results
            
        except Exception as e:
            logger.error(f"Error ranking documents: {e}")
            return []
    
    @cached
    def search(self, query: str, pdf_paths: List[Union[str, Path]], 
               top_k: int = 5) -> List[Dict[str, Any]]:
        """Search across multiple PDF documents for content relevant to a query.
        
        Args:
            query: Search query
            pdf_paths: List of paths to PDF files
            top_k: Number of top results to return
            
        Returns:
            List of dictionaries containing search results
        """
        logger.info(f"Searching {len(pdf_paths)} documents for: {query}")
        
        try:
            # Embed query
            query_vector = self._embed(query)
            
            # Process documents in parallel
            corpus = []
            metadata = []
            
            def process_document(pdf_path):
                pdf_path = Path(pdf_path)
                doc_results = []
                try:
                    if not pdf_path.exists():
                        logger.warning(f"PDF file not found: {pdf_path}")
                        return []
                        
                    # Extract rich text blocks
                    for txt, pno, section in self._get_rich_blocks(pdf_path):
                        doc_results.append({
                            "path": str(pdf_path),
                            "filename": pdf_path.name,
                            "page": pno,
                            "text": txt,
                            "section": section or "Unknown section",
                            "preview": txt[:90] + "..."
                        })
                except Exception as e:
                    logger.error(f"Error processing document {pdf_path}: {e}")
                return doc_results
            
            # Process documents in parallel
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                all_results = list(executor.map(process_document, pdf_paths))
            
            # Flatten results
            for doc_results in all_results:
                for result in doc_results:
                    metadata.append(result)
                    corpus.append(result["text"])
            
            if not corpus:
                logger.warning("No text extracted from documents")
                return []
                
            # Embed corpus and calculate similarity scores
            logger.info(f"Embedding corpus of {len(corpus)} text blocks")
            corpus_vectors = self._embed(corpus, batch_size=BATCH_SIZE)
            scores = util.cos_sim(query_vector, corpus_vectors)[0]

            # Get top results
            k = min(top_k, len(corpus))
            top_results = torch.topk(scores, k)
            
            # Format results
            results = [
                {
                    "document": metadata[i]["filename"],
                    "path": metadata[i]["path"],
                    "page": metadata[i]["page"],
                    "section": metadata[i]["section"],
                    "preview": metadata[i]["preview"],
                    "score": round(float(top_results.values[r]), 4),
                    "rank": r + 1
                }
                for r, i in enumerate(top_results.indices)
            ]
            
            logger.info(f"Found {len(results)} results for query")
            return results
            
        except Exception as e:
            logger.error(f"Error searching documents: {e}")
            return []
    
    def find_similar_content(self, source_pdf: Union[str, Path], target_pdfs: List[Union[str, Path]], 
                            similarity_threshold: float = 0.7, top_k: int = 10) -> List[Dict[str, Any]]:
        """Find similar content between a source PDF and target PDFs.
        
        Args:
            source_pdf: Path to the source PDF file
            target_pdfs: List of paths to target PDF files
            similarity_threshold: Minimum similarity score (0-1)
            top_k: Maximum number of results to return
            
        Returns:
            List of dictionaries containing similarity matches
        """
        logger.info(f"Finding similar content between {source_pdf} and {len(target_pdfs)} target documents")
        
        try:
            source_pdf = Path(source_pdf)
            
            # Extract source blocks
            source_blocks = self._get_rich_blocks(source_pdf)
            if not source_blocks:
                logger.warning(f"No content extracted from source PDF: {source_pdf}")
                return []
                
            # Extract source text
            source_texts = [block[0] for block in source_blocks]
            source_metadata = [
                {"page": block[1], "section": block[2] or "Unknown section", "text": block[0]}
                for block in source_blocks
            ]
            
            # Embed source texts
            source_vectors = self._embed(source_texts)
            
            # Process target documents
            target_corpus = []
            target_metadata = []
            
            for target_pdf in target_pdfs:
                target_pdf = Path(target_pdf)
                try:
                    # Skip source document if it's in the target list
                    if target_pdf.samefile(source_pdf):
                        continue
                        
                    # Extract target blocks
                    target_blocks = self._get_rich_blocks(target_pdf)
                    for txt, pno, section in target_blocks:
                        target_corpus.append(txt)
                        target_metadata.append({
                            "path": str(target_pdf),
                            "filename": target_pdf.name,
                            "page": pno,
                            "section": section or "Unknown section",
                            "text": txt
                        })
                except Exception as e:
                    logger.error(f"Error processing target document {target_pdf}: {e}")
            
            if not target_corpus:
                logger.warning("No content extracted from target documents")
                return []
                
            # Embed target corpus
            target_vectors = self._embed(target_corpus)
            
            # Calculate similarity matrix
            similarity_matrix = util.cos_sim(source_vectors, target_vectors)
            
            # Find matches above threshold
            matches = []
            for source_idx, similarities in enumerate(similarity_matrix):
                # Get indices where similarity is above threshold
                high_scores = torch.where(similarities >= similarity_threshold)[0]
                
                if len(high_scores) == 0:
                    continue
                    
                # Get scores and indices of top matches
                scores, indices = torch.topk(similarities[high_scores], min(top_k, len(high_scores)))
                target_indices = high_scores[indices]
                
                # Add matches to results
                for score_idx, target_idx in enumerate(target_indices):
                    score = scores[score_idx].item()
                    source_info = source_metadata[source_idx]
                    target_info = target_metadata[target_idx]
                    
                    matches.append({
                        "source_document": source_pdf.name,
                        "source_page": source_info["page"],
                        "source_section": source_info["section"],
                        "target_document": target_info["filename"],
                        "target_page": target_info["page"],
                        "target_section": target_info["section"],
                        "similarity_score": round(score, 4),
                        "source_preview": source_info["text"][:100] + "...",
                        "target_preview": target_info["text"][:100] + "..."
                    })
            
            # Sort by similarity score
            matches.sort(key=lambda x: x["similarity_score"], reverse=True)
            
            # Limit to top_k overall matches
            matches = matches[:top_k]
            
            logger.info(f"Found {len(matches)} similar content matches above threshold {similarity_threshold}")
            return matches
            
        except Exception as e:
            logger.error(f"Error finding similar content: {e}")
            return []