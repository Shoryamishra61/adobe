import React, { useEffect, useRef } from 'react';

const PdfViewer = ({ url, meta, onSelect }) => {
  const div = useRef(null);

  useEffect(() => {
    if (!window.AdobeDC) return;
    const view = new window.AdobeDC.View({
      clientId: process.env.REACT_APP_ADOBE_KEY, // Loads from .env
      divId: div.current.id
    });
    view.previewFile({
      content: { location: { url } },
      metaData: { fileName: meta }
    });
    view.registerCallback(
      window.AdobeDC.View.Enum.CallbackType.PDF_VIEWER_EVENT,
      e => e.type === "PREVIEW_SELECTION_END" && onSelect(e.data),
      {}
    );
  }, [url, meta, onSelect]);

  return <div ref={div} id="adobe-dc-view" style={{ height: '100vh', width: '100%' }} />;
};

export default PdfViewer; 