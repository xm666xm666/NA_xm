import React from 'react';
import ReactDOM from 'react-dom/client';
import '@douyinfe/semi-ui/dist/css/semi.css';
import 'react-toastify/dist/ReactToastify.css';
import './i18n';
import './index.css';
import App from './App';
import { dashboardBaseURL, dashboardEnv } from './helpers/api';
import { setStatusData, setUserData } from './helpers/data';

async function fetchDashboardData(path) {
  const response = await fetch(`${dashboardBaseURL}${path}`, {
    cache: 'no-store',
    credentials: 'same-origin',
    headers: { Accept: 'application/json' },
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok || !payload?.success) {
    throw new Error(payload?.message || `看板初始化失败（HTTP ${response.status}）`);
  }
  return payload.data;
}

function renderBootstrapError(error) {
  const root = document.getElementById('root');
  const container = document.createElement('div');
  container.className = 'dashboard-bootstrap';
  const content = document.createElement('div');
  const message = document.createElement('div');
  message.textContent = error.message || '看板加载失败，请稍后重试。';
  const retry = document.createElement('button');
  retry.type = 'button';
  retry.textContent = '重新加载';
  retry.addEventListener('click', () => window.location.reload());
  content.append(message, retry);
  container.append(content);
  root.replaceChildren(container);
}

async function bootstrapDashboard() {
  if (!dashboardEnv) throw new Error('缺少看板环境参数，请从 NA信息页重新打开。');
  const [status, user] = await Promise.all([
    fetchDashboardData('/api/status'),
    fetchDashboardData('/api/user/self'),
  ]);
  setStatusData(status);
  setUserData(user);
  document.title = `性能参数 · ${dashboardEnv.toUpperCase()}`;
  const bootstrap = { env: dashboardEnv, status, user };
  window.NA_PLATFORM_DASHBOARD = bootstrap;
  ReactDOM.createRoot(document.getElementById('root')).render(
    <React.StrictMode>
      <App bootstrap={bootstrap} />
    </React.StrictMode>,
  );
}

bootstrapDashboard().catch(renderBootstrapError);
