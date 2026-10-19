import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import pkg from '@douyinfe/vite-plugin-semi';
const { vitePluginSemi } = pkg;
import path from 'node:path';

export default defineConfig({
  root: __dirname,
  publicDir: false,
  base: '/static/platform-edit/',
  plugins: [react(), vitePluginSemi({ cssLayer: true })],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  build: {
    emptyOutDir: true,
    outDir: '../../static/platform-edit',
    rollupOptions: {
      input: path.resolve(__dirname, 'platform-edit.html'),
    },
  },
});
