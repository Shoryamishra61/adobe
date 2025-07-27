# DocuSphere Webapp

## Setup
1. Install dependencies:
   ```sh
   npm install
   ```
2. Add your Adobe PDF Embed API key to a `.env` file:
   ```sh
   echo REACT_APP_ADOBE_KEY=your_adobe_pdf_embed_key_here > .env
   ```
3. Start the development server:
   ```sh
   npm start
   ```

## Features
- PDF viewing with Adobe PDF Embed SDK
- Bi-directional chart ↔ table highlighting
- Smart glossary (hover for definitions)
- ELI5 summaries
- Cross-PDF concept map
- Collaborative sticky-notes export
- Live persona tuning slider

See the main project README for backend/API details. 