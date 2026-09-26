import {readFileSync} from 'node:fs';
import * as visibility from './frontend-visibility.js';

// Runs before HTML is served, so hidden sections never reach the browser DOM.
// Rebuild and restart after changing a flag.
export function renderFrontendVisibility(html, flags = visibility) {
  const rendered = html.replace(
    /<!-- ECHO_IF (SHOW_[A-Z_]+) -->([\s\S]*?)<!-- ECHO_ENDIF -->/g,
    (_, name, content) => {
      if (typeof flags[name] !== 'boolean') throw new Error(`Unknown frontend flag: ${name}`);
      return flags[name] ? content : '';
    },
  );
  if (flags.SHOW_RESEARCH_PAGE) return rendered;
  // Also removes the optional '·' separator before a research link (public guide navigation).
  return rendered.replace(/(?:[ \t]*·[ \t]*)?<a\b[^>]*\bhref=(["'])([^"']+)\1[^>]*>[\s\S]*?<\/a>/gi,
    (link, _quote, href) => /^(?:\/|\.\/)?research(?:\.html)?\/?(?:[?#].*)?$/.test(href) ? '' : link);
}

export function frontendVisibilityPlugin() {
  return {
    name: 'echo-frontend-visibility',
    transformIndexHtml: {order: 'pre', handler: html => renderFrontendVisibility(html)},
    generateBundle() {
      // Keep the documentation source intact; filter only its served navigation.
      this.emitFile({type: 'asset', fileName: 'README.html', source: renderFrontendVisibility(
        readFileSync(new URL('./public/README.html', import.meta.url), 'utf8'))});
    },
  };
}
