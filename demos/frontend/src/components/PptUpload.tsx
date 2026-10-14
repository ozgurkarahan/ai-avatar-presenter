import React, { useState, useRef } from 'react';
import { uploadPresentation, type Presentation } from '../services/api';

interface Props {
  onUploaded: (presentation: Presentation) => void;
}

const styles: Record<string, React.CSSProperties> = {
  dropZone: {
    border: '2px dashed #ccc',
    borderRadius: '12px',
    padding: '40px 20px',
    textAlign: 'center' as const,
    cursor: 'pointer',
    transition: 'border-color 0.2s, background 0.2s',
  },
  dropZoneActive: {
    borderColor: '#005599',
    background: '#f0f7ff',
  },
  icon: {
    fontSize: '48px',
    marginBottom: '12px',
  },
  button: {
    marginTop: '16px',
    padding: '10px 24px',
    background: '#005599',
    color: 'white',
    border: 'none',
    borderRadius: '8px',
    fontSize: '14px',
    cursor: 'pointer',
  },
  error: {
    color: '#c0392b',
    marginTop: '12px',
    fontSize: '14px',
  },
  loading: {
    color: '#005599',
    marginTop: '12px',
    fontSize: '14px',
  },
};

export default function PptUpload({ onUploaded }: Props) {
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = async (file: File) => {
    if (!file.name.endsWith('.pptx')) {
      setError('Please upload a .pptx file');
      return;
    }
    setError('');
    setLoading(true);
    try {
      const result = await uploadPresentation(file);
      onUploaded(result);
    } catch (e: any) {
      setError(e.message || 'Upload failed');
    } finally {
      setLoading(false);
    }
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    if (e.dataTransfer.files.length) handleFile(e.dataTransfer.files[0]);
  };

  return (
    <div
      style={{ ...styles.dropZone, ...(dragging ? styles.dropZoneActive : {}) }}
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      onClick={() => inputRef.current?.click()}
    >
      <div style={styles.icon}>📄</div>
      <div>Drag & drop a .pptx file here</div>
      <div style={{ color: '#999', marginTop: '4px' }}>or click to browse</div>
      <input
        ref={inputRef}
        type="file"
        accept=".pptx"
        style={{ display: 'none' }}
        onChange={(e) => {
          if (e.target.files?.length) handleFile(e.target.files[0]);
        }}
      />
      {loading && <div style={styles.loading}>⏳ Uploading and parsing...</div>}
      {error && <div style={styles.error}>❌ {error}</div>}
    </div>
  );
}
