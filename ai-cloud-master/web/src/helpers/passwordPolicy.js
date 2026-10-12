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

const MINIMUM_PASSWORD_LENGTH = 8;
const MAXIMUM_PASSWORD_LENGTH = 20;
const MAXIMUM_BCRYPT_PASSWORD_BYTES = 72;

// Keep this set aligned with common/password.go so the frontend gives the same feedback as the backend.
const COMMON_WEAK_PASSWORDS = new Set([
  '000000',
  '111111',
  '123456',
  '12345678',
  '123456789',
  '1234567890',
  '1q2w3e4r',
  '1qaz2wsx',
  'abc123',
  'admin',
  'admin123',
  'admin1234',
  'admin1234!',
  'admin@123',
  'letmein',
  'password',
  'password1',
  'password1!',
  'password123',
  'password@123',
  'qwerty',
  'qwerty123',
  'qwerty123!',
  'root',
  'root123',
  'test1234',
  'welcome',
]);

// validatePasswordStrength returns an inline error message, or an empty string when the password is valid.
export function validatePasswordStrength(password) {
  if (password === '') {
    return '密码不能为空';
  }

  const characterLength = Array.from(password).length;
  if (characterLength < MINIMUM_PASSWORD_LENGTH) {
    return '密码长度至少为8个字符';
  }
  if (characterLength > MAXIMUM_PASSWORD_LENGTH) {
    return '密码长度不能超过20个字符';
  }
  if (
    new TextEncoder().encode(password).length > MAXIMUM_BCRYPT_PASSWORD_BYTES
  ) {
    return '密码 UTF-8 编码不能超过72字节';
  }
  if (COMMON_WEAK_PASSWORDS.has(password.trim().toLowerCase())) {
    return '密码过于常见，请更换更强的密码';
  }

  const categories = [
    /\p{Lu}/u.test(password),
    /\p{Ll}/u.test(password),
    /\p{Nd}/u.test(password),
    /[\p{P}\p{S}]/u.test(password),
  ].filter(Boolean).length;
  if (categories < 3) {
    return '密码必须包含大写字母、小写字母、数字、特殊符号中的至少三类';
  }
  return '';
}
