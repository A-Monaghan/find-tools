import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import { ErrorBoundary } from './components/ErrorBoundary';
import { ToastProvider } from './components/ToastContext';
import { UnifiedConfigProvider } from './context/UnifiedConfigContext';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <ToastProvider>
        <UnifiedConfigProvider>
          <App />
        </UnifiedConfigProvider>
      </ToastProvider>
    </ErrorBoundary>
  </React.StrictMode>,
);