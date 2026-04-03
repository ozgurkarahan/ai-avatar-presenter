import React from 'react';

interface Props {
  value: string;
  onChange: (lang: string) => void;
}

// Languages with native DragonHD voices are marked with ✅
// Others use multilingual en-US-Ava as fallback
const LANGUAGES = [
  { code: 'en-US', label: '🇬🇧 English' },
  { code: 'fr-FR', label: '🇫🇷 French' },
  { code: 'es-ES', label: '🇪🇸 Spanish' },
  { code: 'de-DE', label: '🇩🇪 German' },
  { code: 'ja-JP', label: '🇯🇵 Japanese' },
  { code: 'zh-CN', label: '🇨🇳 Chinese' },
  { code: 'it-IT', label: '🇮🇹 Italian' },
  { code: 'pt-BR', label: '🇧🇷 Portuguese' },
  { code: 'ko-KR', label: '🇰🇷 Korean' },
  { code: 'ar-SA', label: '🇸🇦 Arabic' },
];

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    gap: '8px',
    alignItems: 'center',
  },
  label: {
    fontSize: '13px',
    color: 'rgba(255,255,255,0.8)',
  },
  select: {
    padding: '6px 28px 6px 10px',
    border: '2px solid rgba(255,255,255,0.4)',
    borderRadius: '6px',
    background: 'rgba(255,255,255,0.15)',
    color: 'white',
    fontSize: '13px',
    cursor: 'pointer',
    appearance: 'none' as const,
    backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' fill='white' viewBox='0 0 16 16'%3E%3Cpath d='M1.5 5.5l6.5 6 6.5-6'/%3E%3C/svg%3E")`,
    backgroundRepeat: 'no-repeat',
    backgroundPosition: 'right 8px center',
    minWidth: '160px',
  },
};

export default function LanguageSelector({ value, onChange }: Props) {
  return (
    <div style={styles.container}>
      <span style={styles.label}>🌐</span>
      <select
        style={styles.select}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {LANGUAGES.map((lang) => (
          <option key={lang.code} value={lang.code} style={{ color: '#333', background: 'white' }}>
            {lang.label}
          </option>
        ))}
      </select>
    </div>
  );
}
