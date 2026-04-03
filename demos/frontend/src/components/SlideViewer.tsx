import React, { useRef, useEffect } from 'react';
import { type Presentation } from '../services/api';

interface Props {
  presentation: Presentation;
  currentSlide: number;
  onSlideChange: (index: number) => void;
  language: string;
  onVideoPlayingChange?: (playing: boolean) => void;
  autoPlayVideo?: boolean;
}

const styles: Record<string, React.CSSProperties> = {
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '16px',
  },
  title: {
    fontSize: '16px',
    fontWeight: 600,
  },
  nav: {
    display: 'flex',
    gap: '8px',
    alignItems: 'center',
  },
  navBtn: {
    padding: '6px 14px',
    background: '#005599',
    color: 'white',
    border: 'none',
    borderRadius: '6px',
    cursor: 'pointer',
    fontSize: '13px',
  },
  navBtnDisabled: {
    opacity: 0.4,
    cursor: 'not-allowed',
  },
  slideContainer: {
    aspectRatio: '16/9',
    background: 'linear-gradient(135deg, #ffffff 0%, #f0f4f8 100%)',
    borderRadius: '10px',
    padding: '40px 48px',
    border: '1px solid #d1d5db',
    boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
    display: 'flex',
    flexDirection: 'column' as const,
    justifyContent: 'center',
    position: 'relative' as const,
    overflow: 'hidden',
  },
  slideImageContainer: {
    aspectRatio: '16/9',
    background: '#000',
    borderRadius: '10px',
    border: '1px solid #d1d5db',
    boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
    position: 'relative' as const,
    overflow: 'hidden',
  },
  slideImage: {
    width: '100%',
    height: '100%',
    objectFit: 'contain' as const,
  },
  slideVideo: {
    width: '100%',
    height: '100%',
    objectFit: 'contain' as const,
    background: '#000',
  },
  pptxIframeContainer: {
    aspectRatio: '16/9',
    borderRadius: '10px',
    border: '1px solid #d1d5db',
    boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
    overflow: 'hidden',
  },
  pptxIframe: {
    width: '100%',
    height: '100%',
    border: 'none',
  },
  slideNumber: {
    position: 'absolute' as const,
    bottom: '12px',
    right: '20px',
    fontSize: '12px',
    color: '#999',
    fontWeight: 500,
  },
  slideTitle: {
    fontSize: '26px',
    fontWeight: 700,
    marginBottom: '20px',
    color: '#003366',
    lineHeight: 1.3,
    borderBottom: '3px solid #005599',
    paddingBottom: '12px',
  },
  slideBody: {
    fontSize: '16px',
    lineHeight: 1.8,
    whiteSpace: 'pre-wrap' as const,
    color: '#333',
  },
  bulletList: {
    listStyleType: 'none',
    padding: 0,
    margin: 0,
  },
  bulletItem: {
    fontSize: '16px',
    lineHeight: 1.8,
    color: '#333',
    paddingLeft: '20px',
    position: 'relative' as const,
    marginBottom: '4px',
  },
  notesSection: {
    marginTop: '16px',
    padding: '14px',
    background: '#fff8e1',
    borderRadius: '8px',
    border: '1px solid #ffe082',
  },
  notesLabel: {
    fontSize: '12px',
    fontWeight: 600,
    color: '#f57f17',
    textTransform: 'uppercase' as const,
    marginBottom: '6px',
  },
  notesText: {
    fontSize: '14px',
    lineHeight: 1.5,
    whiteSpace: 'pre-wrap' as const,
    color: '#555',
  },
  counter: {
    fontSize: '13px',
    color: '#666',
  },
};

function formatBody(body: string) {
  if (!body) return null;
  const lines = body.split('\n').filter((l) => l.trim());
  if (lines.length <= 1) {
    return <div style={styles.slideBody}>{body}</div>;
  }
  return (
    <ul style={styles.bulletList}>
      {lines.map((line, i) => (
        <li key={i} style={styles.bulletItem}>
          <span style={{ position: 'absolute', left: 0, color: '#005599', fontWeight: 700 }}>•</span>
          {line.trim()}
        </li>
      ))}
    </ul>
  );
}

export default function SlideViewer({ presentation, currentSlide, onSlideChange, language, onVideoPlayingChange, autoPlayVideo = false }: Props) {
  const slide = presentation.slides[currentSlide];
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [imgError, setImgError] = React.useState(false);

  // Reset image error state when slide changes
  useEffect(() => { setImgError(false); }, [currentSlide, slide?.image_url]);

  // Auto-play the video when the avatar triggers it during presentation mode
  useEffect(() => {
    if (autoPlayVideo && videoRef.current) {
      setTimeout(() => videoRef.current?.play().catch(() => {}), 100);
    }
  }, [autoPlayVideo, slide?.video_url]);

  if (!slide) return <div>No slides found.</div>;

  const displayNotes = language === 'en-US'
    ? slide.notes
    : (slide.translated_notes?.[language] || slide.notes);

  // Build Office Online embed URL when pptx_url is available from Blob Storage
  // wdSlidePage (1-based) navigates the viewer to the current slide
  const officeEmbedUrl = presentation.pptx_url
    ? `https://view.officeapps.live.com/op/embed.aspx?src=${encodeURIComponent(presentation.pptx_url)}&wdSlidePage=${currentSlide + 1}`
    : null;

  return (
    <div>
      <div style={styles.header}>
        <div style={styles.title}>
          📊 {presentation.filename}
        </div>
        <div style={styles.nav}>
          <button
            type="button"
            style={{ ...styles.navBtn, ...(currentSlide === 0 ? styles.navBtnDisabled : {}) }}
            disabled={currentSlide === 0}
            onClick={() => onSlideChange(currentSlide - 1)}
          >
            ◀ Prev
          </button>
          <span style={styles.counter}>
            {currentSlide + 1} / {presentation.slide_count}
          </span>
          <button
            type="button"
            style={{ ...styles.navBtn, ...(currentSlide >= presentation.slide_count - 1 ? styles.navBtnDisabled : {}) }}
            disabled={currentSlide >= presentation.slide_count - 1}
            onClick={() => onSlideChange(currentSlide + 1)}
          >
            Next ▶
          </button>
        </div>
      </div>

      {slide.video_url ? (
        <div style={styles.slideImageContainer}>
          <video
            ref={videoRef}
            src={slide.video_url}
            poster={slide.image_url}
            style={styles.slideVideo}
            controls
            playsInline
            onPlay={() => onVideoPlayingChange?.(true)}
            onPause={() => onVideoPlayingChange?.(false)}
            onEnded={() => onVideoPlayingChange?.(false)}
          />
        </div>
      ) : slide.image_url && !imgError ? (
        <div style={styles.slideImageContainer}>
          <img
            key={slide.image_url}
            src={slide.image_url}
            alt={slide.title || `Slide ${currentSlide + 1}`}
            style={styles.slideImage}
            onError={() => setImgError(true)}
          />
        </div>
      ) : officeEmbedUrl ? (
        <div style={styles.pptxIframeContainer}>
          <iframe
            key={`${presentation.id}-${currentSlide}`}
            src={officeEmbedUrl}
            style={styles.pptxIframe}
            title={presentation.filename}
            allowFullScreen
          />
        </div>
      ) : (
        <div style={styles.slideContainer}>
          {slide.title && <div style={styles.slideTitle}>{slide.title}</div>}
          {formatBody(slide.body)}
          <div style={styles.slideNumber}>Slide {currentSlide + 1}</div>
        </div>
      )}

      {displayNotes && (
        <div style={styles.notesSection}>
          <div style={styles.notesLabel}>
            🗒️ Speaker Notes {language !== 'en-US' && `(${language})`}
          </div>
          <div style={styles.notesText}>{displayNotes}</div>
        </div>
      )}
    </div>
  );
}
