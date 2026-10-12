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

import { normalizeLogoPath } from './logo';

export function setStatusData(data) {
  localStorage.setItem('status', JSON.stringify(data));
  localStorage.setItem('system_name', data.system_name);
  // 写入缓存前降级历史非法值，避免后续页面直接加载任意 URL。
  localStorage.setItem('logo', normalizeLogoPath(data.logo));
  localStorage.setItem('footer_html', data.footer_html);
  localStorage.setItem('quota_per_unit', data.quota_per_unit);
  // 兼容：保留旧字段，同时写入新的额度展示类型
  localStorage.setItem('display_in_currency', data.display_in_currency);
  localStorage.setItem('quota_display_type', data.quota_display_type || 'USD');
  localStorage.setItem('enable_drawing', data.enable_drawing);
  localStorage.setItem('enable_task', data.enable_task);
  localStorage.setItem('enable_data_export', data.enable_data_export);
  localStorage.setItem('chats', JSON.stringify(data.chats));
  localStorage.setItem(
    'data_export_default_time',
    data.data_export_default_time,
  );
  localStorage.setItem(
    'default_collapse_sidebar',
    data.default_collapse_sidebar,
  );
  localStorage.setItem('mj_notify_enabled', data.mj_notify_enabled);
  if (data.chat_link) {
    // localStorage.setItem('chat_link', data.chat_link);
  } else {
    localStorage.removeItem('chat_link');
  }
  if (data.chat_link2) {
    // localStorage.setItem('chat_link2', data.chat_link2);
  } else {
    localStorage.removeItem('chat_link2');
  }
  if (data.docs_link) {
    localStorage.setItem('docs_link', data.docs_link);
  } else {
    localStorage.removeItem('docs_link');
  }
}

export function setUserData(data) {
  localStorage.setItem('user', JSON.stringify(data));
}

// 统一兼容分页包装和裸数组两种接口返回，避免业务层重复判断。
export function extractPayloadArray(payload) {
  const items = payload?.items || payload || [];
  return Array.isArray(items) ? items : [];
}

// 统一处理筛选表单重置后的延迟回调，保持现有刷新时机不变。
export function resetFormAndRefresh(formApi, callback, afterReset) {
  if (!formApi) {
    return;
  }
  formApi.reset();
  if (typeof afterReset === 'function') {
    afterReset();
  }
  setTimeout(() => {
    if (typeof callback === 'function') {
      callback();
    }
  }, 100);
}
