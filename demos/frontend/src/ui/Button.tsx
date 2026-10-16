import React from 'react';
import { Link, type LinkProps } from 'react-router-dom';
import type { LucideIcon } from 'lucide-react';

export type ButtonVariant = 'primary' | 'outline' | 'ghost' | 'danger' | 'link';
export type ButtonSize = 'sm' | 'md' | 'lg';

interface CommonProps {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** Leading icon. */
  icon?: LucideIcon;
  /** Trailing icon. */
  iconRight?: LucideIcon;
  /** Square icon-only button — requires `aria-label`. */
  iconOnly?: boolean;
  block?: boolean;
  /** Shows a spinner and disables the button. */
  busy?: boolean;
}

export function buttonClass({ variant = 'outline', size = 'md', iconOnly, block }: CommonProps, extra?: string): string {
  return [
    'btn',
    variant !== 'outline' && `btn--${variant}`,
    size !== 'md' && `btn--${size}`,
    iconOnly && 'btn--icon',
    block && 'btn--block',
    extra,
  ].filter(Boolean).join(' ');
}

function Content({ icon: Icon, iconRight: IconRight, busy, children }: CommonProps & { children?: React.ReactNode }) {
  return (
    <>
      {busy ? <span className="spinner" aria-hidden /> : Icon && <Icon aria-hidden />}
      {children}
      {IconRight && <IconRight aria-hidden />}
    </>
  );
}

export type ButtonProps = CommonProps & React.ButtonHTMLAttributes<HTMLButtonElement>;

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant, size, icon, iconRight, iconOnly, block, busy, className, children, type = 'button', disabled, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      className={buttonClass({ variant, size, iconOnly, block }, className)}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      {...rest}
    >
      <Content icon={icon} iconRight={iconRight} busy={busy}>{children}</Content>
    </button>
  );
});

export type ButtonLinkProps = CommonProps & LinkProps;

/** A react-router link styled as a button. */
export function ButtonLink({ variant, size, icon, iconRight, iconOnly, block, className, children, ...rest }: ButtonLinkProps) {
  return (
    <Link className={buttonClass({ variant, size, iconOnly, block }, className)} {...rest}>
      <Content icon={icon} iconRight={iconRight}>{children}</Content>
    </Link>
  );
}
