import React, { useState, useEffect } from 'react';
import PptUpload from './components/PptUpload';
import SlideViewer from './components/SlideViewer';
import AvatarPanel from './components/AvatarPanel';
import LanguageSelector from './components/LanguageSelector';
import QaChat from './components/QaChat';
import type { Presentation } from './services/api';
import { initializeTeams, isInTeams, getTeamsTheme, onTeamsThemeChange } from './services/teams';

// Teams theme palette
const themes: Record<string, { bg: string; surface: string; text: string; shadow: string }> = {
  default: { bg: '#f5f7fa', surface: '#ffffff', text: '#1a1a2e', shadow: '0 1px 4px rgba(0,0,0,0.08)' },
  dark:    { bg: '#1f1f1f', surface: '#2d2d2d', text: '#e0e0e0', shadow: '0 1px 4px rgba(0,0,0,0.3)' },
  contrast:{ bg: '#000000', surface: '#1a1a1a', text: '#ffffff', shadow: '0 1px 4px rgba(255,255,255,0.1)' },
};

function getStyles(inTeams: boolean, theme: string): Record<string, React.CSSProperties> {
  const t = themes[theme] ?? themes.default;
  return {
    container: {
      minHeight: '100vh',
      background: t.bg,
      color: t.text,
    },
    header: {
      background: 'linear-gradient(135deg, #003366 0%, #005599 100%)',
      color: 'white',
      padding: inTeams ? '8px 16px' : '16px 32px',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
    },
    headerTitle: {
      fontSize: inTeams ? '16px' : '22px',
      fontWeight: 700,
    },
    headerSubtitle: {
      fontSize: inTeams ? '11px' : '13px',
      opacity: 0.8,
    },
    main: {
      maxWidth: '1400px',
      margin: '0 auto',
      padding: inTeams ? '12px' : '24px',
    },
    grid: {
      display: 'grid',
      gridTemplateColumns: '1fr 380px',
      gap: inTeams ? '16px' : '24px',
      marginTop: inTeams ? '12px' : '20px',
    },
    leftPanel: {
      display: 'flex',
      flexDirection: 'column' as const,
      gap: inTeams ? '12px' : '20px',
    },
    rightPanel: {
      display: 'flex',
      flexDirection: 'column' as const,
      gap: inTeams ? '12px' : '20px',
    },
    card: {
      background: t.surface,
      borderRadius: '12px',
      padding: inTeams ? '14px' : '20px',
      boxShadow: t.shadow,
    },
  };
}

export default function App() {
  const [presentation, setPresentation] = useState<Presentation | null>(null);
  const [currentSlide, setCurrentSlide] = useState(0);
  const [language, setLanguage] = useState('en-US');
  const [inTeams, setInTeams] = useState(false);
  const [teamsTheme, setTeamsTheme] = useState('default');

  useEffect(() => {
    initializeTeams().then((detected) => {
      setInTeams(detected);
      if (detected) {
        setTeamsTheme(getTeamsTheme());
        onTeamsThemeChange((theme) => setTeamsTheme(theme));
      }
    });
  }, []);

  const styles = getStyles(inTeams, teamsTheme);

  return (
    <div style={styles.container}>
      <header style={styles.header}>
        <div>
          <div style={styles.headerTitle}>🎙️ AI Presenter</div>
          {!inTeams && (
            <div style={styles.headerSubtitle}>AI Avatar Presentation Assistant</div>
          )}
        </div>
        {presentation && (
          <LanguageSelector value={language} onChange={setLanguage} />
        )}
      </header>

      <main style={styles.main}>
        {!presentation ? (
          <div style={{ ...styles.card, maxWidth: '600px', margin: inTeams ? '24px auto' : '60px auto', textAlign: 'center' as const }}>
            <h2 style={{ marginBottom: '16px' }}>Upload a Presentation</h2>
            <p style={{ color: teamsTheme === 'default' ? '#666' : '#aaa', marginBottom: '24px' }}>
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
