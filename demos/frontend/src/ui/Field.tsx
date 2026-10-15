import React, { useId } from 'react';

/**
 * Labelled form field. Pass a single control as child; it receives the
 * generated `id` and `aria-describedby` automatically.
 */
export function Field({ label, hint, error, inline, size, className, children, labelHidden }: {
  label: React.ReactNode;
  hint?: React.ReactNode;
  error?: React.ReactNode;
  inline?: boolean;
  size?: 'sm' | 'md';
  labelHidden?: boolean;
  className?: string;
  children: React.ReactElement<{ id?: string; 'aria-describedby'?: string; 'aria-invalid'?: boolean }>;
}) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const errId = error ? `${id}-err` : undefined;
  const control = React.cloneElement(children, {
    id: children.props.id ?? id,
    'aria-describedby': [hintId, errId].filter(Boolean).join(' ') || undefined,
    'aria-invalid': error ? true : undefined,
  });
  return (
    <div className={['field', inline && 'field--inline', size === 'sm' && 'field--sm', className].filter(Boolean).join(' ')}>
      <label className={labelHidden ? 'sr-only' : 'field__label'} htmlFor={children.props.id ?? id}>{label}</label>
      {control}
      {hint && <span className="field__hint" id={hintId}>{hint}</span>}
      {error && <span className="field__error" id={errId}>{error}</span>}
    </div>
  );
}

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  function Input({ className, ...rest }, ref) {
    return <input ref={ref} className={['field__control', className].filter(Boolean).join(' ')} {...rest} />;
  },
);

export const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  function Textarea({ className, ...rest }, ref) {
    return <textarea ref={ref} className={['field__control', className].filter(Boolean).join(' ')} {...rest} />;
  },
);

/** Native <select> with editorial styling (keeps full keyboard/a11y behaviour). */
export const Select = React.forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement> & { wrapClassName?: string }>(
  function Select({ className, wrapClassName, children, ...rest }, ref) {
    return (
      <span className={['field__select', wrapClassName].filter(Boolean).join(' ')}>
        <select ref={ref} className={['field__control', className].filter(Boolean).join(' ')} {...rest}>{children}</select>
      </span>
    );
  },
);

export function Checkbox({ label, className, ...rest }: { label: React.ReactNode } & React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label className={['checkbox', className].filter(Boolean).join(' ')}>
      <input type="checkbox" {...rest} />
      {label}
    </label>
  );
}
