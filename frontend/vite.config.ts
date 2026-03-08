// frontend/vite.config.ts
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

export default defineConfig({
    plugins: [react()],
    resolve: {
        alias: {
            '@': path.resolve(__dirname, './src'),
            '@pages': path.resolve(__dirname, './src/pages'),
            '@services': path.resolve(__dirname, './src/services'),
            '@app-types': path.resolve(__dirname, './src/types'),
            '@components': path.resolve(__dirname, './src/components'),
        },
    },
    server: {
        port: 3000,
        proxy: {
            // Proxy ALL API + WebSocket calls through Vite dev server → backend
            // This eliminates CORS issues entirely in development
            '/api': {
                target: 'http://localhost:8080',
                changeOrigin: true,
                secure: false,
            },
            '/ws': {
                target: 'ws://localhost:8080',
                ws: true,
                changeOrigin: true,
            },
            '/auth': {
                target: 'http://localhost:8080',
                changeOrigin: true,
            },
            '/health': {
                target: 'http://localhost:8080',
                changeOrigin: true,
            },
            '/metrics': {
                target: 'http://localhost:8080',
                changeOrigin: true,
            },
        },
    },
});
