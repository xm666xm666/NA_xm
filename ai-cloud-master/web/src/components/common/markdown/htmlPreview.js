/*
Copyright (C) 2025 QuantumNous

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>.

For commercial licensing, please contact support@quantumnous.com
*/

// The iframe sandbox blocks script execution; this CSP independently blocks external resources and navigation helpers.
export const HTML_PREVIEW_CSP = [
  "default-src 'none'",
  "script-src 'none'",
  "connect-src 'none'",
  "frame-src 'none'",
  "style-src 'unsafe-inline'",
  'img-src data: blob:',
  'font-src data:',
  'media-src data: blob:',
  "form-action 'none'",
  "base-uri 'none'",
  "object-src 'none'",
].join('; ');

// buildSandboxedHtmlDocument places all security controls before untrusted model HTML is parsed.
export function buildSandboxedHtmlDocument(htmlCode) {
  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8">
    <meta http-equiv="Content-Security-Policy" content="${HTML_PREVIEW_CSP}">
    <meta name="referrer" content="no-referrer">
    <style>
      html, body { margin: 0; padding: 0; overflow-wrap: anywhere; }
      body { min-height: 100%; }
    </style>
  </head>
  <body>${htmlCode}</body>
</html>`;
}
