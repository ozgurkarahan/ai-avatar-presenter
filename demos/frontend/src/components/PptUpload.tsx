import React, { useState } from 'react';
import { FileUp } from 'lucide-react';
import { uploadPresentation, type Presentation } from '../services/api';
import { Alert, Dropzone } from '../ui';

interface Props {
  onUploaded: (presentation: Presentation) => void;
}

export default function PptUpload({ onUploaded }: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

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

  return (
    <div className="stack" style={{ '--stack-gap': 'var(--sp-3)' } as React.CSSProperties}>
      <Dropzone
        onFile={handleFile}
        accept=".pptx"
        busy={loading}
        icon={FileUp}
        title="Drop a .pptx deck here"
        busyTitle="Uploading and parsing…"
        hint="or click to browse — speaker notes become the narration"
      />
      {error && <Alert tone="error" onClose={() => setError('')}>{error}</Alert>}
    </div>
  );
}
