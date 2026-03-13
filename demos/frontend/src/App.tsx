import React, { useState } from 'react';
import PptUpload from './components/PptUpload';
import SlideViewer from './components/SlideViewer';
import AvatarPanel from './components/AvatarPanel';
import LanguageSelector from './components/LanguageSelector';
import QaChat from './components/QaChat';
import type { Presentation } from './services/api';

const styles: Record<string, React.CSSProperties> = {
  container: {
    minHeight: '100vh',
    background: '#f5f7fa',
    color: '#1a1a2e',
  },
  header: {
    background: 'linear-gradient(135deg, #003366 0%, #005599 100%)',
    color: 'white',
    padding: '16px 32px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
  },
  headerTitle: {
    fontSize: '22px',
    fontWeight: 700,
  },
  headerSubtitle: {
    fontSize: '13px',
    opacity: 0.8,
  },
  main: {
    maxWidth: '1400px',
    margin: '0 auto',
    padding: '24px',
  },
  grid: {
    display: 'grid',
    gridTemplateColumns: '1fr 380px',
    gap: '24px',
    marginTop: '20px',
  },
  leftPanel: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '20px',
  },
  rightPanel: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '20px',
  },
  card: {
    background: 'white',
    borderRadius: '12px',
    padding: '20px',
    boxShadow: '0 1px 4px rgba(0,0,0,0.08)',
  },
};

export default function App() {
  const [presentation, setPresentation] = useState<Presentation | null>(null);
  const [currentSlide, setCurrentSlide] = useState(0);
  const [language, setLanguage] = useState('en-US');

  return (
    <div style={styles.container}>
      <header style={styles.header}>
        <div>
          <div style={styles.headerTitle}>🎙️ AI Presenter</div>
          <div style={styles.headerSubtitle}>AI Avatar Presentation Assistant</div>
        </div>
        {presentation && (
          <LanguageSelector value={language} onChange={setLanguage} />
        )}
      </header>

      <main style={styles.main}>
        {!presentation ? (
          <div style={{ ...styles.card, maxWidth: '600px', margin: '60px auto', textAlign: 'center' as const }}>
            <h2 style={{ marginBottom: '16px' }}>Upload a Presentation</h2>
            <p style={{ color: '#666', marginBottom: '24px' }}>
              Upload a PowerPoint file (.pptx) with speaker notes to get started.
              The AI avatar will present your slides with multilingual text-to-speech.
            </p>
            <PptUpload onUploaded={setPresentation} />
          </div>
        ) : (
          <div style={styles.grid}>
            <div style={styles.leftPanel}>
              <div style={styles.card}>
                <SlideViewer
                  presentation={presentation}
                  currentSlide={currentSlide}
                  onSlideChange={setCurrentSlide}
                  language={language}
                />
              </div>
            </div>
            <div style={styles.rightPanel}>
              <div style={styles.card}>
                <AvatarPanel
                  presentation={presentation}
                  currentSlide={currentSlide}
                  language={language}
                />
              </div>
              <div style={styles.card}>
                <QaChat
                  presentationId={presentation.id}
                  slideIndex={currentSlide}
                />
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
