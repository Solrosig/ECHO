import {defineConfig} from 'vite';
import {fileURLToPath} from 'node:url';
import {frontendVisibilityPlugin} from './frontend-visibility-build.js';
export default defineConfig({
  plugins:[frontendVisibilityPlugin()],
  worker:{format:'es'},
  build:{copyPublicDir:false,outDir:'dist/client',target:'esnext',rollupOptions:{input:{
    home:fileURLToPath(new URL('./index.html',import.meta.url)),studio:fileURLToPath(new URL('./studio.html',import.meta.url)),
    listen:fileURLToPath(new URL('./listen.html',import.meta.url)),
    research:fileURLToPath(new URL('./research.html',import.meta.url))
  }}}
});
