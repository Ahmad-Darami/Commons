import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  // Relative paths, so the built app works from any sub-path (GitHub Pages serves it under /Commons/).
  base: './',
  build: { chunkSizeWarningLimit: 2000 },
});
