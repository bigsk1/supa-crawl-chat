import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

// Determine the API target based on environment
const API_TARGET = process.env.DOCKER_ENV 
  ? 'http://api:8001'  // Use the service name in Docker
  : 'http://localhost:8001';

console.log(`Vite config using API target: ${API_TARGET}`);

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 3001,
    host: '0.0.0.0', // Allow connections from all network interfaces
    proxy: {
      // Single proxy configuration for all API endpoints
      '/api': {
        target: API_TARGET,
        changeOrigin: true,
        secure: false,
        rewrite: (path) => path, // Don't rewrite the path
        configure: (proxy, _options) => {
          const noisy = (url: string | undefined) =>
            url?.includes('/api/crawl/status') || url?.includes('/api/crawl/activity');
          proxy.on('error', (err, _req, _res) => {
            console.log('proxy error', err);
          });
          proxy.on('proxyReq', (_proxyReq, req, _res) => {
            if (!noisy(req.url)) {
              console.log('Sending Request:', req.method, req.url);
            }
          });
          proxy.on('proxyRes', (proxyRes, req, _res) => {
            if (!noisy(req.url)) {
              console.log('Received Response:', proxyRes.statusCode, req.url);
            }
          });
        },
      },
    },
  },
  build: {
    // Ignore TypeScript errors during build
    sourcemap: true,
  },
}); 