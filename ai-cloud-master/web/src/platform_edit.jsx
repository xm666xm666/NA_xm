import React, { useEffect, useState } from 'react';
import ReactDOM from 'react-dom/client';
import { LocaleProvider } from '@douyinfe/semi-ui';
import zh_CN from '@douyinfe/semi-ui/lib/es/locale/source/zh_CN';
import { StatusProvider } from './context/Status';
import { API } from './helpers';
import './i18n/i18n';
import '../node_modules/@douyinfe/semi-ui/dist/css/semi.css';
import './index.css';
import EditChannelModal from './components/table/channels/modals/EditChannelModal';
import EditTokenModal from './components/table/tokens/modals/EditTokenModal';

const params = new URLSearchParams(window.location.search);
const kind = params.get('kind') === 'tokens' ? 'tokens' : 'channels';
const recordId = Number(params.get('id') || 0);
const env = params.get('env') || '';

API.defaults.baseURL = `/api/platform/${encodeURIComponent(env)}/upstream`;
API.defaults.headers.common['Cache-Control'] = 'no-store';

const originalGet = API.get.bind(API);
const EMPTY_SUCCESS_RESPONSE = { data: { success: true, data: [] } };

API.get = async (url, config = {}) => {
  const requestUrl = String(url || '');
  if (requestUrl.startsWith('/api/user/2fa/status')) {
    try {
      return await originalGet(url, { ...config, skipErrorHandler: true });
    } catch (error) {
      if (error.response?.status === 404) {
        return { data: { success: true, data: { enabled: false } } };
      }
      throw error;
    }
  }
  if (requestUrl.startsWith('/api/user/passkey')) {
    try {
      return await originalGet(url, { ...config, skipErrorHandler: true });
    } catch (error) {
      if (error.response?.status === 404) {
        return { data: { success: true, data: { enabled: false } } };
      }
      throw error;
    }
  }
  if (requestUrl.startsWith('/api/prefill_group')) {
    try {
      return await originalGet(url, { ...config, skipErrorHandler: true });
    } catch (error) {
      if (error.response?.status === 404) {
        return EMPTY_SUCCESS_RESPONSE;
      }
      throw error;
    }
  }
  if (requestUrl.startsWith('/api/channel/models')) {
    try {
      return await originalGet(url, { ...config, skipErrorHandler: true });
    } catch (error) {
      if (error.response?.status !== 404) {
        throw error;
      }
      try {
        const fallback = await originalGet('/api/models', {
          ...config,
          skipErrorHandler: true,
        });
        const models = (fallback.data?.data || []).map((model) =>
          typeof model === 'string' ? { id: model } : model,
        );
        return { ...fallback, data: { ...fallback.data, data: models } };
      } catch (fallbackError) {
        if (fallbackError.response?.status === 404) {
          return EMPTY_SUCCESS_RESPONSE;
        }
        throw fallbackError;
      }
    }
  }
  return originalGet(url, config);
};

const bootstrapAuth = async () => {
  const response = await fetch('/auth/me', { credentials: 'same-origin' });
  if (!response.ok) throw new Error('NA 会话已失效，请重新登录');
  const payload = await response.json();
  if (payload?.csrf_token) {
    API.defaults.headers.common['X-CSRF-Token'] = payload.csrf_token;
  }
};

const PlatformEditPage = () => {
  const [ready, setReady] = useState(false);
  const [error, setError] = useState('');
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    bootstrapAuth()
      .then(() => setReady(true))
      .catch((exc) => setError(exc.message || 'NA 会话已失效，请重新登录'));
  }, []);

  const handleClose = () => {
    setVisible(false);
    window.parent?.postMessage({ type: 'na-platform-edit-close', changed: true }, '*');
  };

  const modalProps = {
    refresh: () => {},
    handleClose,
    visible,
    visiable: visible,
  };

  if (error) {
    return <div className="platform-edit-state platform-edit-error">{error}</div>;
  }
  if (!ready) {
    return <div className="platform-edit-state platform-edit-loading">正在加载编辑器...</div>;
  }
  return (
    <React.StrictMode>
      <StatusProvider>
        <LocaleProvider locale={zh_CN}>
          {kind === 'channels' ? (
            <EditChannelModal editingChannel={{ id: recordId }} {...modalProps} />
          ) : (
            <EditTokenModal editingToken={{ id: recordId }} {...modalProps} />
          )}
        </LocaleProvider>
      </StatusProvider>
    </React.StrictMode>
  );
};

ReactDOM.createRoot(document.getElementById('root')).render(<PlatformEditPage />);
