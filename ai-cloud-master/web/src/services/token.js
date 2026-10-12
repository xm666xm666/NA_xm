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

import { API } from '../helpers';

/**
 * 统一收口令牌相关请求，避免组件层分散拼接接口地址。
 */
export const TokenService = {
  /**
   * 获取当前用户可用模型列表。
   */
  async getUserModels() {
    const response = await API.get('/api/user/models');
    return response.data;
  },

  /**
   * 获取当前用户可用分组列表。
   */
  async getUserGroups() {
    const response = await API.get('/api/user/self/groups');
    return response.data;
  },

  /**
   * 获取当前分组下模型配额已配置的维度能力，供令牌页限制可选限流维度。
   */
  async getModelQuotaCapabilities(group = '') {
    const response = await API.get('/api/token/model_quota_capabilities', {
      params: group ? { group } : undefined,
    });
    return response.data;
  },

  /**
   * 获取指定模型在当前分组下可映射的关联配额池候选。
   */
  async getModelQuotaCandidates(modelName, group = '') {
    const response = await API.get('/api/token/model_quota_candidates', {
      params: {
        model_name: modelName,
        ...(group ? { group } : {}),
      },
    });
    return response.data;
  },

  /**
   * 获取单个令牌详情。
   */
  async getToken(id) {
    const response = await API.get(`/api/token/${id}`);
    return response.data;
  },

  /**
   * 获取令牌分页列表。
   */
  async getTokens(page, size) {
    const response = await API.get(`/api/token/?p=${page}&size=${size}`);
    return response.data;
  },

  /**
   * 搜索令牌列表。
   */
  async searchTokens(keyword, token) {
    const response = await API.get(
      `/api/token/search?keyword=${encodeURIComponent(keyword)}&token=${encodeURIComponent(token)}`,
    );
    return response.data;
  },

  /**
   * 创建令牌。
   */
  async createToken(payload) {
    const response = await API.post('/api/token/', payload);
    return response.data;
  },

  /**
   * 更新令牌。
   */
  async updateToken(payload) {
    const response = await API.put('/api/token/', payload);
    return response.data;
  },

  /**
   * 更新令牌状态。
   */
  async updateTokenStatus(payload) {
    const response = await API.put('/api/token/?status_only=true', payload);
    return response.data;
  },

  /**
   * 删除单个令牌。
   */
  async deleteToken(id) {
    const response = await API.delete(`/api/token/${id}/`);
    return response.data;
  },

  /**
   * 批量删除令牌。
   */
  async batchDeleteTokens(ids) {
    const response = await API.post('/api/token/batch', { ids });
    return response.data;
  },
};
