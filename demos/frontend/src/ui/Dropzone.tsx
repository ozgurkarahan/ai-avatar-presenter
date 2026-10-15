import React, { useRef, useState } from 'react';
import { Upload, type LucideIcon } from 'lucide-react';

/**
 * Keyboard- and mouse-operable file drop zone. The hidden <input type=file>
 * receives `inputProps` (e.g. a `data-testid`) so tests can set files directly.
 */
export function Dropzone({
  onFile, accept, busy = false, disabled = false, title, busyTitle = 'Uploading…', hint, icon: Icon = Upload,
  inputProps, className, children,
}: {
  onFile: (file: File) => void;
  accept?: string;
  busy?: boolean;
  disabled?: boolean;
  title: React.ReactNode;
  busyTitle?: React.ReactNode;
  hint?: React.ReactNode;
  icon?: LucideIcon;
  inputProps?: Record<string, unknown>;
  className?: string;
  children?: React.ReactNode;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const inactive = busy || disabled;

  function pick(files: FileList | null | undefined) {
    const f = files?.[0];
    if (f && !inactive) onFile(f);
  }

  return (
    <div
      role="button"
      tabIndex={inactive ? -1 : 0}
      aria-disabled={inactive || undefined}
      aria-busy={busy || undefined}
      className={['dropzone', over && 'is-dragover', busy && 'is-busy', className].filter(Boolean).join(' ')}
      onClick={() => { if (!inactive) inputRef.current?.click(); }}
      onKeyDown={(e) => {
        if ((e.key === 'Enter' || e.key === ' ') && !inactive) { e.preventDefault(); inputRef.current?.click(); }
      }}
      onDragOver={(e) => { e.preventDefault(); if (!inactive) setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); pick(e.dataTransfer.files); }}
    >
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        hidden
        onChange={(e) => { pick(e.target.files); e.target.value = ''; }}
        {...inputProps}
      />
      <span className="dropzone__icon" aria-hidden>{busy ? <span className="spinner" /> : <Icon />}</span>
      <span className="dropzone__title">{busy ? busyTitle : title}</span>
      {hint && <span className="dropzone__hint">{hint}</span>}
      {children}
    </div>
  );
}
