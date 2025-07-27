import React, { useState } from 'react';

const SemanticSearch = () => {
  const [query, setQuery] = useState('');
  const [searchResults, setSearchResults] = useState(null);
  const [isSearching, setIsSearching] = useState(false);
  const [error, setError] = useState(null);

  const handleSearch = async () => {
    if (!query.trim()) return;

    setIsSearching(true);
    setError(null);

    try {
      // This would connect to the /api/rank endpoint
      // For demo purposes, showing mock results
      setTimeout(() => {
        setSearchResults({
          query: query,
          results: [
            {
              document: "financial_report_2023.pdf",
              section: "Revenue Analysis",
              relevance_score: 0.92,
              content: "The company's revenue increased by 15% year-over-year, driven primarily by strong performance in the technology sector...",
              page: 12
            },
            {
              document: "market_analysis.pdf", 
              section: "Market Trends",
              relevance_score: 0.87,
              content: "Market analysis shows significant growth potential in emerging markets, with technology adoption rates exceeding expectations...",
              page: 8
            },
            {
              document: "quarterly_review.pdf",
              section: "Performance Metrics",
              relevance_score: 0.81,
              content: "Key performance indicators demonstrate sustained growth across all major business units, with technology investments yielding positive returns...",
              page: 5
            }
          ]
        });
        setIsSearching(false);
      }, 2000);
    } catch (err) {
      setError('Search failed. Please try again.');
      setIsSearching(false);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter') {
      handleSearch();
    }
  };

  return (
    <div className="semantic-search">
      <h2>🔍 Semantic Document Search</h2>
      <p>Search across all processed documents using natural language queries</p>

      <div className="search-container">
        <div className="search-input-group">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Ask a question about your documents... (e.g., 'What are the revenue trends?')"
            className="search-input"
            disabled={isSearching}
          />
          <button 
            onClick={handleSearch}
            disabled={isSearching || !query.trim()}
            className="search-button"
          >
            {isSearching ? '🔄' : '🔍'}
          </button>
        </div>

        <div className="search-examples">
          <h4>Try these example queries:</h4>
          <div className="example-queries">
            <button 
              className="example-query"
              onClick={() => setQuery('What are the main financial highlights?')}
            >
              "What are the main financial highlights?"
            </button>
            <button 
              className="example-query"
              onClick={() => setQuery('Show me performance metrics and KPIs')}
            >
              "Show me performance metrics and KPIs"
            </button>
            <button 
              className="example-query"
              onClick={() => setQuery('What are the market trends and opportunities?')}
            >
              "What are the market trends and opportunities?"
            </button>
          </div>
        </div>
      </div>

      {isSearching && (
        <div className="search-loading">
          <div className="loading-animation"></div>
          <p>🧠 Analyzing documents with AI-powered semantic search...</p>
        </div>
      )}

      {error && (
        <div className="search-error">
          <p>❌ {error}</p>
        </div>
      )}

      {searchResults && (
        <div className="search-results">
          <div className="results-header">
            <h3>📊 Search Results for: "{searchResults.query}"</h3>
            <p>Found {searchResults.results.length} relevant sections</p>
          </div>

          <div className="results-list">
            {searchResults.results.map((result, index) => (
              <div key={index} className="result-item">
                <div className="result-header">
                  <div className="result-title">
                    <h4>📄 {result.document}</h4>
                    <span className="result-section">{result.section}</span>
                  </div>
                  <div className="result-meta">
                    <span className="relevance-score">
                      {Math.round(result.relevance_score * 100)}% match
                    </span>
                    <span className="page-number">Page {result.page}</span>
                  </div>
                </div>
                <div className="result-content">
                  <p>{result.content}</p>
                </div>
                <div className="result-actions">
                  <button className="action-btn small">View Full Document</button>
                  <button className="action-btn small secondary">Export Section</button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {!searchResults && !isSearching && (
        <div className="search-placeholder">
          <div className="placeholder-content">
            <h3>🎯 Intelligent Document Search</h3>
            <div className="feature-grid">
              <div className="feature-item">
                <span className="feature-icon">🧠</span>
                <h4>AI-Powered</h4>
                <p>Uses advanced language models to understand context and meaning</p>
              </div>
              <div className="feature-item">
                <span className="feature-icon">⚡</span>
                <h4>Fast Results</h4>
                <p>Instant search across all your processed documents</p>
              </div>
              <div className="feature-item">
                <span className="feature-icon">🎯</span>
                <h4>Precise Matching</h4>
                <p>Finds relevant content even with different wording</p>
              </div>
              <div className="feature-item">
                <span className="feature-icon">📊</span>
                <h4>Ranked Results</h4>
                <p>Results sorted by relevance with confidence scores</p>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default SemanticSearch;