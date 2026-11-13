import axios from 'axios';
import { showError } from './utils';

export const dashboardEnv = new URLSearchParams(window.location.search).get('env')?.trim() || '';
export const dashboardBaseURL = `/api/platform/${encodeURIComponent(dashboardEnv)}/dashboard`;

export const API = axios.create({
  baseURL: dashboardBaseURL,
  headers: {
    'Cache-Control': 'no-store',
  },
});

const originalGet = API.get.bind(API);
const inFlightGetRequests = new Map();

API.get = (url, config = {}) => {
  if (config?.disableDuplicate) return originalGet(url, config);
  const key = `${url}?${config.params ? JSON.stringify(config.params) : '{}'}`;
  if (inFlightGetRequests.has(key)) return inFlightGetRequests.get(key);
  const pendingRequest = originalGet(url, config).finally(() => {
    inFlightGetRequests.delete(key);
  });
  inFlightGetRequests.set(key, pendingRequest);
  return pendingRequest;
};

API.interceptors.response.use(
  (response) => response,
  (error) => {
    if (!error.config?.skipErrorHandler) showError(error);
    return Promise.reject(error);
  },
);
