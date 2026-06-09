import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import App from './App';
import { applyHubDirection } from './lib/direction';
import { installGlobalErrorReporting } from './lib/client-logger';
import './index.css';

// App-level dir seam (TASK-251) — LTR default, RTL via VITE_HUB_DIR=rtl.
applyHubDirection();

// Capture every uncaught error / unhandled rejection → server log sink so
// nothing in the SPA fails silently.
installGlobalErrorReporting();

// SPA entry point.
// - BrowserRouter for client-side routing.
// - React Query for API caching across Graph / Board / Cognition / Search pages.
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 15_000,
    },
  },
});

const rootEl = document.getElementById('root');
if (!rootEl) {
  throw new Error('missing #root element in index.html');
}

ReactDOM.createRoot(rootEl).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
