# DocuSphere

## Overview
DocuSphere is a two-round solution for PDF knowledge extraction and visualization:
- **Backend:** CPU-only Docker microservice (Flask) for PDF outline, table, and semantic embedding extraction.
- **Frontend:** React + Adobe PDF Embed UI for AI summaries, linked highlights, auto-charts, and cross-document maps.

## Backend (round1)

### Build & Run (Docker)
```sh
cd round1
# Build Docker image
docker build -t docusphere-backend .
# Run container
docker run -p 8000:8000 docusphere-backend
```

### API Endpoints
- `POST /analyze` — Upload PDF(s), get JSON (outline, tables, etc.)
- `POST /rank` — Persona-based section ranking

### Model Size
- MiniLM model: <200 MB compressed
- CPU-only: No GPU required

## Frontend (webapp)

### Setup
```sh
cd webapp
npm install
npm start
```

### Features
- PDF viewing (Adobe PDF Embed SDK)
- Bi-directional chart ↔ table highlighting
- Smart glossary (hover for definitions)
- ELI5 summaries
- Cross-PDF concept map
- Collaborative sticky-notes export
- Live persona tuning slider

## Guarantee
- All code runs on CPU only (no CUDA/GPU required)
- Docker image ≤ 1 GB

---
See `approach_explanation.md` for technical details and `webapp/` for UI code. 