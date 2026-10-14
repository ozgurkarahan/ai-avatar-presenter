import React from 'react';

interface State { error: Error | null }

/** Last-resort guard so an unexpected render error never blanks the whole app. */
export default class ErrorBoundary extends React.Component<{ children: React.ReactNode; resetKey?: string }, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('[ErrorBoundary]', error, info.componentStack);
  }

  componentDidUpdate(prev: { resetKey?: string }) {
    if (prev.resetKey !== this.props.resetKey && this.state.error) this.setState({ error: null });
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div role="alert" style={{ maxWidth: 640, margin: '60px auto', padding: 24, textAlign: 'center',
        background: 'white', borderRadius: 12, boxShadow: '0 4px 20px rgba(0, 51, 102, 0.08)' }}>
        <div style={{ fontSize: 40 }} aria-hidden>⚠️</div>
        <h2 style={{ color: '#003366' }}>Something went wrong on this page</h2>
        <p style={{ color: '#64748b' }}>Try reloading, or pick another section from the navigation bar.</p>
        <button
          type="button"
          onClick={() => window.location.reload()}
          style={{ background: '#005599', color: 'white', border: 'none', borderRadius: 8,
            padding: '8px 18px', fontWeight: 600, cursor: 'pointer' }}
        >
          Reload
        </button>
      </div>
    );
  }
}
