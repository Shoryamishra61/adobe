import json
from pathlib import Path
from sentence_transformers import SentenceTransformer, util
import fitz
import torch
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from collections import Counter

# Download necessary NLTK data
try:
    stopwords.words('english')
except LookupError:
    nltk.download('stopwords')
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')

model = SentenceTransformer('all-MiniLM-L6-v2')

def extract_keywords(text):
    stop_words = set(stopwords.words('english'))
    words = word_tokenize(text.lower())
    filtered_words = [word for word in words if word.isalnum() and word not in stop_words]
    return [word for word, _ in Counter(filtered_words).most_common(10)]

def rank(config_path, pdfs_path, top_k=5):
    with open(config_path) as f:
        config = json.load(f)

    persona = config.get("persona", {})
    job_to_be_done = config.get("job_to_be_done", {})

    # Extract keywords from persona and job description
    persona_keywords = extract_keywords(persona.get('role', ''))
    job_keywords = extract_keywords(job_to_be_done.get('task', ''))
    query_keywords = list(set(persona_keywords + job_keywords))

    if not query_keywords:
        return []

    query = " ".join(query_keywords)
    query_embedding = model.encode(query, convert_to_tensor=True)

    results = []
    for pdf_path in pdfs_path.glob("*.pdf"):
        doc = fitz.open(pdf_path)
        for pno, page in enumerate(doc, 1):
            text = page.get_text()
            if text:
                passages = text.split("\n\n")
                for passage in passages:
                    if len(passage.strip()) > 50: # Only consider passages with some substance
                        passage_embedding = model.encode(passage, convert_to_tensor=True)
                        score = util.pytorch_cos_sim(query_embedding, passage_embedding)[0][0]

                        # Add a bonus for keyword matches
                        passage_keywords = extract_keywords(passage)
                        keyword_bonus = len(set(query_keywords) & set(passage_keywords)) * 0.1
                        final_score = float(score) + keyword_bonus

                        results.append({
                            "document": pdf_path.name,
                            "section_title": " ".join(passage.split()[:10]) + "...", # Use first 10 words as title
                            "importance_rank": final_score,
                            "page_number": pno,
                            "refined_text": passage
                        })
        doc.close()

    results.sort(key=lambda x: x["importance_rank"], reverse=True)
    return results[:top_k]

def find_similar_content(source_path, target_paths, similarity_threshold=0.7, top_k=10):
    # Placeholder for similarity search
    return {"message": "Similarity search not yet implemented."}

def cluster_documents(documents, document_names, num_clusters=3, algorithm='kmeans', min_similarity=0.3):
    # Placeholder for clustering
    return {"message": "Clustering not yet implemented."}

def generate_summary(text, summary_type='executive', max_length=500, metadata=None, outline=None):
    # Placeholder for summarization
    return "Summary not yet implemented."

def extract_key_points(text, metadata=None):
    # Placeholder for key point extraction
    return ["Key points not yet implemented."]

def extract_topics(text, metadata=None):
    # Placeholder for topic extraction
    return ["Topics not yet implemented."]

class SemanticRanker:
    def __init__(self):
        pass

    def rank(self, config_path, base_path, top_k=5):
        return rank(config_path, base_path, top_k)

    def search(self, query, pdf_paths, top_k=5):
        return {"message": "Search not yet implemented."}

    def find_similar_content(self, source_path, target_paths, similarity_threshold=0.7, top_k=10):
        return find_similar_content(source_path, target_paths, similarity_threshold, top_k)

    def cluster_documents(self, documents, document_names, num_clusters=3, algorithm='kmeans', min_similarity=0.3):
        return cluster_documents(documents, document_names, num_clusters, algorithm, min_similarity)

    def generate_summary(self, text, summary_type='executive', max_length=500, metadata=None, outline=None):
        return generate_summary(text, summary_type, max_length, metadata, outline)

    def extract_key_points(self, text, metadata=None):
        return extract_key_points(text, metadata)

    def extract_topics(self, text, metadata=None):
        return extract_topics(text, metadata)