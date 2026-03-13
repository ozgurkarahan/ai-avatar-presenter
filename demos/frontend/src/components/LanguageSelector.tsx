import React from 'react';

interface Props {
  value: string;
  onChange: (lang: string) => void;
}

const LANGUAGES = [
  { code: 'en-US', label: '🇬🇧 English', flag: '🇬🇧' },
  { code: 'fr-FR', label: '🇫🇷 French', flag: '🇫🇷' },
  { code: 'es-ES', label: '🇪🇸 Spanish', flag: '🇪🇸' },
];

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    gap: '6px',
    alignItems: 'center',
  },
  label: {
    fontSize: '13px',
    color: 'rgba(255,255,255,0.8)',
    marginRight: '4px',
  },
  button: {
    padding: '6px 12px',
    border: '2px solid transparent',
    borderRadius: '6px',
    background: 'rgba(255,255,255,0.15)',
    color: 'white',
    fontSize: '13px',
    cursor: 'pointer',
    transition: 'all 0.15s',
  },
  active: {
    borderColor: 'white',
    background: 'rgba(255,255,255,0.3)',
  },
};

export default function LanguageSelector({ value, onChange }: Props) {
  return (
    <div style={styles.container}>
      <span style={styles.label}>Language:</span>
      {LANGUAGES.map((lang) => (
        <button
          key={lang.code}
          style={{
            ...styles.button,
            ...(value === lang.code ? styles.active : {}),
          }}
          onClick={() => onChange(lang.code)}
        >
          {lang.label}
        </button>
      ))}
    </div>
  );
}
