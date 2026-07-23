import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    // Vite 5.4+ rechaza peticiones cuyo encabezado Host no esté en esta
    // lista (protección contra DNS-rebinding). Sin esto, entrar por un
    // túnel de ngrok da "Blocked request. This host is not allowed".
    //
    // '.ngrok-free.dev' con punto inicial acepta cualquier subdominio, así
    // no hay que editar este archivo cada vez que ngrok asigna una URL
    // nueva (el plan gratuito la cambia en cada arranque).
    //
    // Solo aplica al servidor de DESARROLLO. En producción el sitio se
    // sirve compilado detrás de Nginx, que no usa nada de esto.
    allowedHosts: [
      'localhost',
      '.ngrok-free.dev',
      '.ngrok-free.app',
      '.ngrok.io',
    ],
    proxy: {
      '/api': {
        target: 'http://sicavs_backend:5000',
        changeOrigin: true,
      }
    }
  },
});