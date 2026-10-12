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

import { API, extractPayloadArray } from '../helpers';

// 模型配额服务，集中处理页面所需的读取与保存接口。
export const modelQuotaService = {
  // list 获取模型配额列表，传入 group 时只返回该分组相关项。
  async list(group = '') {
    const params = group ? { group } : undefined;
    const response = await API.get('/api/model_quota/', { params });
    return response.data;
  },

  // listGroups 获取可用于模型配额筛选和令牌配置的分组列表。
  async listGroups() {
    const response = await API.get('/api/group/');
    return response.data;
  },

  // updateQuota 保存普通模型项或共享池项的额度配置。
  async updateQuota(payload) {
    const response = await API.put('/api/model_quota/', payload);
    return response.data;
  },

  // saveSharedPool 保存共享池及其成员关系。
  async saveSharedPool(payload) {
    const response = await API.put('/api/model_quota/shared_pool', payload);
    return response.data;
  },

  // getReferences 查询模型配额被哪些令牌限流配置引用。
  async getReferences(id) {
    const response = await API.get(`/api/model_quota/${id}/references`);
    return response.data;
  },

  // deleteQuota 删除普通模型配额项。
  async deleteQuota(id) {
    const response = await API.delete(`/api/model_quota/${id}`);
    return response.data;
  },

  // deleteSharedPool 删除共享池及其成员关系。
  async deleteSharedPool(id) {
    const response = await API.delete(`/api/model_quota/shared_pool/${id}`);
    return response.data;
  },

  // removeSharedPoolTag 将共享池子项恢复为普通模型项。
  async removeSharedPoolTag(id) {
    const response = await API.delete(`/api/model_quota/${id}/shared_pool_tag`);
    return response.data;
  },

  // 复用公共数组提取逻辑，保持原服务导出接口不变。
  extractArrayData: extractPayloadArray,
};

export default modelQuotaService;
