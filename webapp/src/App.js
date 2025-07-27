 import React, { useState, useCallback } from 'react';
import './App.css';
import FileUpload from './components/FileUpload';
import ProcessingStatus from './components/ProcessingStatus';
import ResultsViewer from './components/ResultsViewer';
import SemanticSearch from './components/SemanticSearch';

function App() {
  const [uploadedFiles, setUploadedFiles] = useState([]);
  const [processing, setProcessing] = useState(false);
  const [results, setResults] = useState(null);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('upload');

  const handleFileUpload = useCallback(async (files) => {
    setProcessing(true);
    setError(null);
    setUploadedFiles(files);

    try {
      const formData = new FormData();
      files.forEach(file => {
        formData.append('files', file);
      });

      const response = await fetch('/api/analyze', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      // Handle zip file response
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.style.display = 'none';
      a.href = url;
      a.download = 'pdf_analysis_results.zip';
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);

      // For demo purposes, also fetch individual results
      setResults({
        message: 'Analysis complete! Results downloaded as ZIP file.',
        fileCount: files.length,
        timestamp: new Date().toISOString()
      });
      setActiveTab('results');
    } catch (err) {
      setError(err.message);
    } finally {
      setProcessing(false);
    }
  }, []);

  return (
    <div className="App">
      <header className="app-header">
        <div className="header-content">
          <h1>🚀 Adobe Hackathon 2025</h1>
          <h2>PDF Intelligence Platform</h2>
          <p>Extract, Analyze, and Search PDF Content with AI</p>
        </div>
      </header>

      <nav className="tab-navigation">
        <button 
          className={`tab ${activeTab === 'upload' ? 'active' : ''}`}
          onClick={() => setActiveTab('upload')}
        >
          📄 Upload & Analyze
        </button>
        <button 
          className={`tab ${activeTab === 'search' ? 'active' : ''}`}
          onClick={() => setActiveTab('search')}
        >
          🔍 Semantic Search
        </button>
        <button 
          className={`tab ${activeTab === 'results' ? 'active' : ''}`}
          onClick={() => setActiveTab('results')}
        >
          📊 Results
        </button>
      </nav>

      <main className="main-content">
        {activeTab === 'upload' && (
          <div className="upload-section">
            <FileUpload 
              onFileUpload={handleFileUpload}
              disabled={processing}
            />
            {processing && <ProcessingStatus files={uploadedFiles} />}
            {error && (
              <div className="error-message">
                <h3>❌ Error</h3>
                <p>{error}</p>
              </div>
            )}
          </div>
        )}

        {activeTab === 'search' && (
          <SemanticSearch />
        )}

        {activeTab === 'results' && (
          <ResultsViewer results={results} />
        )}
      </main>

      <footer className="app-footer">
        <div className="footer-content">
          <div className="feature-highlights">
            <div className="feature">
              <h4>🎯 Smart Extraction</h4>
              <p>Tables, text, metadata, and document structure</p>
            </div>
            <div className="feature">
              <h4>🧠 AI-Powered Analysis</h4>
              <p>Document classification and content insights</p>
            </div>
            <div className="feature">
              <h4>⚡ Semantic Search</h4>
              <p>Find relevant content across multiple documents</p>
            </div>
            <div className="feature">
              <h4>📈 Real-time Processing</h4>
              <p>Parallel processing with live progress updates</p>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}

export default App;