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

export const DEFAULT_LOGO_PATH = '/logo.png';

// normalizeLogoPath prevents cached Logo values from loading external or internal-network URLs.
export function normalizeLogoPath(value) {
  const logo = typeof value === 'string' ? value.trim() : '';
  if (!logo.startsWith('/') || logo.startsWith('//') || logo.includes('\\')) {
    return DEFAULT_LOGO_PATH;
  }

  try {
    const base = 'https://logo.invalid';
    const parsed = new URL(logo, base);
    if (parsed.origin !== base) {
      return DEFAULT_LOGO_PATH;
    }
    return `${parsed.pathname}${parsed.search}${parsed.hash}`;
  } catch {
    return DEFAULT_LOGO_PATH;
  }
}
