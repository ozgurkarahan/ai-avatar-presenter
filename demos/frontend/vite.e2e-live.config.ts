// Test-only Vite config for the LIVE end-to-end suite (tests/e2e-live.spec.ts).
//
// Emulates Azure Container Apps Easy Auth in front of a local backend that runs
// with AUTH_MODE=easyauth (tests/e2e_live_server.py): when DECKFM_E2E_PRINCIPAL
// is set, every proxied /api request and /ws upgrade gets the
// X-MS-CLIENT-PRINCIPAL headers ACA would inject after sign-in (admin
// instance); without it the instance is anonymous. Host is preserved so the
// backend's same-origin WebSocket check behaves as in production.
import { defineConfig, mergeConfig } from 'vite';
import base from './vite.config';

const principal = process.env.DECKFM_E2E_PRINCIPAL;
const backend = process.env.DECKFM_E2E_BACKEND ?? 'http://127.0.0.1:8000';
const headers = principal
  ? { 'X-MS-CLIENT-PRINCIPAL': principal, 'X-MS-CLIENT-PRINCIPAL-IDP': 'aad' }
  : undefined;

export default mergeConfig(base, defineConfig({
  server: {
    proxy: {
      '/api': { target: backend, changeOrigin: false, headers },
      '/ws': { target: backend, changeOrigin: false, ws: true, headers },
    },
  },
}));
