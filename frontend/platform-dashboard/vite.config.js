import path from 'node:path';
import { fileURLToPath } from 'node:url';
import react from '@vitejs/plugin-react';
import { defineConfig, transformWithEsbuild } from 'vite';
import semiPlugin from '@douyinfe/vite-plugin-semi';

const directory = path.dirname(fileURLToPath(import.meta.url));
const { vitePluginSemi } = semiPlugin;

export default defineConfig({
  base: '/static/platform-dashboard/',
  plugins: [
    {
      name: 'treat-js-files-as-jsx',
      async transform(code, id) {
        if (!/src\/.*\.js$/.test(id)) return null;
        return transformWithEsbuild(code, id, {
          loader: 'jsx',
          jsx: 'automatic',
        });
      },
    },
    react(),
    vitePluginSemi({ cssLayer: true }),
  ],
  build: {
    outDir: path.resolve(directory, '../../static/platform-dashboard'),
    emptyOutDir: true,
    rollupOptions: {
      input: path.resolve(directory, 'platform-dashboard.html'),
      output: {
        manualChunks: {
          'react-core': ['react', 'react-dom', 'react-router-dom'],
          'semi-ui': ['@douyinfe/semi-icons', '@douyinfe/semi-ui'],
          charts: ['@visactor/react-vchart', '@visactor/vchart'],
          tools: ['axios', 'marked', 'react-toastify'],
          i18n: ['i18next', 'react-i18next'],
        },
      },
    },
  },
});
