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

const inFlightMFASetupRequests = new Map();

// completeMFASetup 统一绑定完成接口的用户数据返回契约。
export const completeMFASetup = async (request, code) => {
  const response = await request({ code });
  if (!response.data.success) {
    throw new Error(response.data.message);
  }
  return response.data.data;
};

// requestMFASetup 按登录用户隔离请求，并让 StrictMode 重挂载共享同一结果。
export const requestMFASetup = (setupKey, request) => {
  if (!inFlightMFASetupRequests.has(setupKey)) {
    const requestPromise = request().finally(() => {
      // 请求结束后释放 single-flight，使失败场景可以重试。
      inFlightMFASetupRequests.delete(setupKey);
    });
    inFlightMFASetupRequests.set(setupKey, requestPromise);
  }
  return inFlightMFASetupRequests.get(setupKey);
};
