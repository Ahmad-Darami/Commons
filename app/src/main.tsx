import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import { useApp } from './store';
import './styles.css';

// Tests and devtools can read app state with ?debug
if (import.meta.env.DEV || new URLSearchParams(location.search).has('debug')) (window as unknown as { __commons: typeof useApp }).__commons = useApp;

createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>);
