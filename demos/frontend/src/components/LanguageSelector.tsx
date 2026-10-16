import { Field, Select } from '../ui';
import '../styles/shared/language-selector.css';

interface Props {
  value: string;
  onChange: (lang: string) => void;
  /** Kept for backwards compatibility: 'light' shows a visible label, 'dark' keeps it screen-reader only. */
  variant?: 'dark' | 'light';
  /** Visible label text (defaults to "Language"). */
  label?: string;
  /** Force the label visible or hidden regardless of `variant`. */
  hideLabel?: boolean;
  className?: string;
}

// Languages with native DragonHD voices; others use multilingual en-US-Ava as fallback.
const LANGUAGES = [
  { code: 'en-US', label: 'English' },
  { code: 'fr-FR', label: 'French' },
  { code: 'es-ES', label: 'Spanish' },
  { code: 'de-DE', label: 'German' },
  { code: 'ja-JP', label: 'Japanese' },
  { code: 'zh-CN', label: 'Chinese' },
  { code: 'it-IT', label: 'Italian' },
  { code: 'pt-BR', label: 'Portuguese' },
  { code: 'ko-KR', label: 'Korean' },
  { code: 'ar-SA', label: 'Arabic' },
];

export default function LanguageSelector({ value, onChange, variant = 'dark', label = 'Language', hideLabel, className }: Props) {
  const labelHidden = hideLabel ?? variant !== 'light';
  return (
    <Field label={label} labelHidden={labelHidden} inline size="sm" className={['language-selector', className].filter(Boolean).join(' ')}>
      <Select value={value} onChange={(e) => onChange(e.target.value)}>
        {LANGUAGES.map((lang) => (
          <option key={lang.code} value={lang.code}>{lang.label}</option>
        ))}
      </Select>
    </Field>
  );
}
