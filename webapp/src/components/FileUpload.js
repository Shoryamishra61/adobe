import React, { useCallback, useState } from 'react';

const FileUpload = ({ onFileUpload, disabled }) => {
  const [dragOver, setDragOver] = useState(false);
  const [selectedFiles, setSelectedFiles] = useState([]);

  const handleDragOver = useCallback((e) => {
    e.preventDefault();
    setDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e) => {
    e.preventDefault();
    setDragOver(false);
  }, []);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    setDragOver(false);
    
    const files = Array.from(e.dataTransfer.files).filter(
      file => file.type === 'application/pdf'
    );
    
    if (files.length > 0) {
      setSelectedFiles(files);
      onFileUpload(files);
    }
  }, [onFileUpload]);

  const handleFileSelect = useCallback((e) => {
    const files = Array.from(e.target.files).filter(
      file => file.type === 'application/pdf'
    );
    
    if (files.length > 0) {
      setSelectedFiles(files);
      onFileUpload(files);
    }
  }, [onFileUpload]);

  const handleUploadClick = useCallback(() => {
    document.getElementById('file-input').click();
  }, []);

  return (
    <div className="file-upload">
      <h2>📄 Upload PDF Documents</h2>
      <p>Drag and drop your PDF files here or click to browse</p>
      
      <div 
        className={`upload-area ${dragOver ? 'dragover' : ''}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={handleUploadClick}
      >
        <div className="upload-icon">📁</div>
        <div className="upload-text">
          <h3>Drop PDF files here</h3>
          <p>or click to browse your computer</p>
          <p className="file-info">Supports multiple PDF files</p>
        </div>
      </div>

      <input
        id="file-input"
        type="file"
        multiple
        accept=".pdf"
        onChange={handleFileSelect}
        className="file-input"
        disabled={disabled}
      />

      <button 
        className="upload-button"
        onClick={handleUploadClick}
        disabled={disabled}
      >
        {disabled ? 'Processing...' : 'Choose Files'}
      </button>

      {selectedFiles.length > 0 && (
        <div className="selected-files">
          <h4>Selected Files ({selectedFiles.length}):</h4>
          <div className="file-list">
            {selectedFiles.map((file, index) => (
              <div key={index} className="file-item">
                <span>📄</span>
                <span>{file.name}</span>
                <span className="file-size">
                  ({(file.size / 1024 / 1024).toFixed(2)} MB)
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default FileUpload;