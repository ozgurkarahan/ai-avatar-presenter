import React from 'react';
import { RotateCcw, TriangleAlert } from 'lucide-react';

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
      <div role="alert" className="crash">
        <div className="empty">
          <span className="empty__icon"><TriangleAlert aria-hidden /></span>
          <h2 className="empty__title">Something went wrong on this page</h2>
          <p className="empty__text">Try reloading, or pick another section from the navigation bar.</p>
          <button type="button" className="btn btn--primary" onClick={() => window.location.reload()}>
            <RotateCcw aria-hidden /> Reload
          </button>
        </div>
      </div>
    );
  }
}
