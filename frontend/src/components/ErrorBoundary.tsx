import { Component } from 'react';
import type { ErrorInfo, ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/**
 * Catches render-time errors in any page so a single crashing route shows a
 * recoverable fallback instead of unmounting the whole app (which would take
 * the sidebar / sync control with it). Resets when "Try again" is clicked.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Surface for debugging; replace with real telemetry if/when available.
    console.error('Page crashed:', error, info.componentStack);
  }

  handleReset = () => this.setState({ error: null });

  render() {
    if (this.state.error) {
      return (
        <div className="p-8 max-w-2xl">
          <div className="flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 p-4">
            <span className="text-red-500 mt-0.5">✕</span>
            <div>
              <p className="text-sm font-semibold text-red-800">Something went wrong on this page</p>
              <p className="text-sm text-red-700 mt-0.5">{this.state.error.message}</p>
              <button
                onClick={this.handleReset}
                className="mt-3 text-sm text-red-700 underline hover:text-red-900"
              >
                Try again
              </button>
            </div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
