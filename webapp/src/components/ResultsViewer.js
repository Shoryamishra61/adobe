import React from 'react';

const ResultsViewer = ({ results }) => {
  if (!results) {
    return (
      <div className="results-viewer">
        <div className="no-results">
          <h2>📊 Analysis Results</h2>
          <p>Upload and process PDF files to see results here</p>
          <div className="demo-features">
            <h3>What you'll get:</h3>
            <ul>
              <li>📄 Document metadata and structure</li>
              <li>📋 Extracted tables in JSON format</li>
              <li>📝 Text content with keyword analysis</li>
              <li>🏷️ Document classification and insights</li>
              <li>📈 Content statistics and metrics</li>
            </ul>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="results-viewer">
      <div className="success-message">
        <h3>✅ Analysis Complete!</h3>
        <p>{results.message}</p>
      </div>

      <div className="results-summary">
        <h3>📊 Processing Summary</h3>
        <div className="summary-grid">
          <div className="summary-item">
            <div className="summary-icon">📄</div>
            <div className="summary-content">
              <h4>Files Processed</h4>
              <p>{results.fileCount}</p>
            </div>
          </div>
          <div className="summary-item">
            <div className="summary-icon">⏰</div>
            <div className="summary-content">
              <h4>Completed At</h4>
              <p>{new Date(results.timestamp).toLocaleString()}</p>
            </div>
          </div>
          <div className="summary-item">
            <div className="summary-icon">💾</div>
            <div className="summary-content">
              <h4>Output Format</h4>
              <p>JSON (ZIP Download)</p>
            </div>
          </div>
        </div>
      </div>

      <div className="sample-output">
        <h3>📋 Sample Output Structure</h3>
        <div className="code-preview">
          <pre>{`{
  "title": "Document Title",
  "metadata": {
    "author": "Author Name",
    "page_count": 42,
    "file_size": 1048576,
    "creation_date": "2024-01-15T10:30:00Z"
  },
  "outline": [
    {
      "level": "H1",
      "text": "Chapter Title",
      "page": 5,
      "font_size": 18,
      "is_bold": true
    }
  ],
  "tables": [
    {
      "page": 10,
      "rows": 5,
      "columns": 3,
      "headers": ["Col1", "Col2", "Col3"],
      "data": [...]
    }
  ],
  "text": [
    {
      "page": 1,
      "text": "Full page content...",
      "keywords": ["keyword1", "keyword2"],
      "word_count": 250
    }
  ],
  "analysis": {
    "document_type": "structured_document",
    "statistics": {
      "word_count": 10500,
      "table_count": 8,
      "heading_count": 25
    }
  }
}`}</pre>
        </div>
      </div>

      <div className="next-steps">
        <h3>🚀 Next Steps</h3>
        <div className="action-buttons">
          <button className="action-btn primary">
            🔍 Try Semantic Search
          </button>
          <button className="action-btn secondary">
            📄 Process More Files
          </button>
          <button className="action-btn secondary">
            📊 View Analytics Dashboard
          </button>
        </div>
      </div>
    </div>
  );
};

export default ResultsViewer;