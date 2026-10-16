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
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { onClose(); return; }
      if (e.key !== 'Tab' || !panelRef.current) return;
      // Cycle Tab focus within the dialog.
      const items = panelRef.current.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), video[controls], [tabindex]:not([tabindex="-1"])',
      );
      if (items.length === 0) { e.preventDefault(); panelRef.current.focus(); return; }
      const first = items[0];
      const last = items[items.length - 1];
      const active = document.activeElement;
      if (e.shiftKey && (active === first || active === panelRef.current)) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && active === last) { e.preventDefault(); first.focus(); }
    };
    // Keep focus inside the modal: anything focusing the page behind is pulled back.
    const onFocusIn = (e: FocusEvent) => {
      const panel = panelRef.current;
      if (panel && e.target instanceof Node && !panel.contains(e.target)) panel.focus();
    };
    document.addEventListener('keydown', onKey);
    document.addEventListener('focusin', onFocusIn);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('focusin', onFocusIn);
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
