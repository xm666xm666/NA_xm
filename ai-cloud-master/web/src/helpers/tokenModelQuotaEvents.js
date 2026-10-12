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

// TOKEN_MODEL_QUOTA_REFRESH_EVENT 用于通知模型配额页重新拉取“令牌名 - 限流配置”和剩余额度。
export const TOKEN_MODEL_QUOTA_REFRESH_EVENT = 'token-model-quota:refresh';

// emitTokenModelQuotaRefresh 在令牌创建、编辑、删除后广播刷新事件。
export const emitTokenModelQuotaRefresh = (detail = {}) => {
  if (typeof window === 'undefined') {
    return;
  }
  window.dispatchEvent(
    new CustomEvent(TOKEN_MODEL_QUOTA_REFRESH_EVENT, {
      detail,
    }),
  );
};
