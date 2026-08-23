import { Component, type ErrorInfo, type ReactNode } from 'react';

// Last-resort safety net. Without it, any uncaught render error in a
// route component (e.g. a Rules-of-Hooks violation) silently unmounts
// the whole tree and the user sees a blank white page with zero clue.
//
// Place at the App root so it catches every screen. Each route still
// owns its own loading/error states for expected failures (network,
// 404, etc.); this only catches programmer errors React itself
// surfaced.

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
  info: ErrorInfo | null;
}

export class ErrorBoundary extends Component<Props, State> {
  override state: State = { error: null, info: null };

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error };
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    this.setState({ info });
    // Surface to dev console; in prod this is also where you'd send to
    // Sentry/Bugsnag.
    console.error('[ErrorBoundary] caught render error', error, info.componentStack);
  }

  private handleReload = (): void => {
    window.location.reload();
  };

  private handleHome = (): void => {
    window.location.assign('/');
  };

  override render(): ReactNode {
    if (!this.state.error) return this.props.children;

    const { error, info } = this.state;
    const stack = (info?.componentStack ?? '').trim();

    return (
      <div
        role="alert"
        style={{
          minHeight: '100vh',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          padding: 24,
          fontFamily: "'JetBrains Mono', monospace",
          background: 'var(--board, #f6f1e7)',
          color: 'var(--ink, #1a1814)',
          gap: 16,
        }}
      >
        <h1 style={{ fontSize: 22, margin: 0 }}>Something broke this screen.</h1>
        <p style={{ margin: 0, color: 'var(--ink-soft, #6b665e)' }}>
          The page hit an uncaught render error. The app is otherwise fine.
        </p>
        <div style={{ display: 'flex', gap: 12 }}>
          <button
            type="button"
            onClick={this.handleReload}
            style={{
              padding: '8px 16px',
              border: '2px solid var(--line, #b8ad9a)',
              background: 'var(--accent, #ea580c)',
              color: '#fff',
              fontFamily: 'inherit',
              cursor: 'pointer',
            }}
          >
            Reload page
          </button>
          <button
            type="button"
            onClick={this.handleHome}
            style={{
              padding: '8px 16px',
              border: '2px solid var(--line, #b8ad9a)',
              background: 'transparent',
              color: 'inherit',
              fontFamily: 'inherit',
              cursor: 'pointer',
            }}
          >
            Go to Hub home
          </button>
        </div>
        <details
          style={{
            maxWidth: 720,
            width: '100%',
            background: 'rgba(0,0,0,0.04)',
            border: '1px solid var(--line, #b8ad9a)',
            borderRadius: 4,
            padding: 12,
            fontSize: 12,
          }}
        >
          <summary style={{ cursor: 'pointer', fontWeight: 600 }}>Error details</summary>
          <div style={{ marginTop: 12 }}>
            <div style={{ fontWeight: 600 }}>{error.name}: {error.message}</div>
            {error.stack && (
              <pre style={{ overflowX: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                {error.stack}
              </pre>
            )}
            {stack && (
              <>
                <div style={{ fontWeight: 600, marginTop: 8 }}>Component stack</div>
                <pre style={{ overflowX: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                  {stack}
                </pre>
              </>
            )}
          </div>
        </details>
      </div>
    );
  }
}
