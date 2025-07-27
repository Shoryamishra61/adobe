import React from 'react';

const ProcessingStatus = ({ files }) => {
  return (
    <div className="processing-status">
      <div className="processing-animation"></div>
      <h3>🔄 Processing Your PDFs...</h3>
      <p>Extracting content, analyzing structure, and generating insights</p>
      
      <div className="processing-steps">
        <div className="step active">
          <span className="step-icon">📄</span>
          <span>Reading PDF files</span>
        </div>
        <div className="step active">
          <span className="step-icon">🔍</span>
          <span>Extracting text and tables</span>
        </div>
        <div className="step active">
          <span className="step-icon">🧠</span>
          <span>Analyzing content structure</span>
        </div>
        <div className="step">
          <span className="step-icon">📊</span>
          <span>Generating insights</span>
        </div>
      </div>

      {files && files.length > 0 && (
        <div className="file-list">
          <h4>Processing Files:</h4>
          {files.map((file, index) => (
            <div key={index} className="file-item">
              <span>⏳</span>
              <span>{file.name}</span>
            </div>
          ))}
        </div>
      )}
      
      <div className="processing-info">
        <p>⚡ Using parallel processing for faster results</p>
        <p>🎯 Extracting tables, text, metadata, and document structure</p>
        <p>🧠 Applying AI-powered content analysis</p>
      </div>
    </div>
  );
};

export default ProcessingStatus;