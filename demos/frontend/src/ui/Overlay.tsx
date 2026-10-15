import React, { useEffect, useRef } from 'react';
import { X } from 'lucide-react';

/** Accessible tablist with arrow-key navigation. Render panels yourself based on `value`. */
export function Tabs<T extends string>({ tabs, value, onChange, label, className }: {
  tabs: { id: T; label: React.ReactNode }[];
  value: T;
  onChange: (id: T) => void;
  label: string;
  className?: string;
}) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  return (
    <div role="tablist" aria-label={label} className={['tabs', className].filter(Boolean).join(' ')}>
      {tabs.map((t, i) => (
        <button
          key={t.id}
          ref={(el) => { refs.current[i] = el; }}
          type="button"
          role="tab"
          className="tabs__tab"
          aria-selected={t.id === value}
          tabIndex={t.id === value ? 0 : -1}
          onClick={() => onChange(t.id)}
          onKeyDown={(e) => {
            const dir = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
            if (!dir) return;
            e.preventDefault();
            const next = (i + dir + tabs.length) % tabs.length;
            onChange(tabs[next].id);
            refs.current[next]?.focus();
          }}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

/**
 * Dialog with scrim, Escape-to-close, initial focus and focus restore.
 * `variant="stage"` gives a dark panel for video players.
 */
export function Modal({ open, onClose, label, variant = 'default', children, className, ...rest }: {
  open: boolean;
  onClose: () => void;
  label: string;
  variant?: 'default' | 'narrow' | 'stage';
  children: React.ReactNode;
  className?: string;
} & React.HTMLAttributes<HTMLDivElement>) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    panelRef.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = overflow;
      previous?.focus?.();
    };
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="modal" onClick={onClose}>
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={label}
        tabIndex={-1}
        className={[
          'modal__panel',
          variant === 'narrow' && 'modal__panel--narrow',
          variant === 'stage' && 'stage',
          className,
        ].filter(Boolean).join(' ')}
        onClick={(e) => e.stopPropagation()}
        {...rest}
      >
        <button
          type="button"
          className={['btn btn--icon btn--sm modal__close', variant === 'stage' ? 'btn--ghost' : ''].join(' ')}
          style={variant === 'stage' ? { color: 'var(--c-on-stage)', borderColor: 'transparent' } : undefined}
          aria-label="Close"
          onClick={onClose}
        >
          <X aria-hidden />
        </button>
        {children}
      </div>
    </div>
  );
}
