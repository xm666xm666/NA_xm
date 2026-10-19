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

function withNormalizedData(payload, data) {
  return {
    ...payload,
    data: { ...(payload?.data || {}), data },
  };
}

function flattenDashboardModels(payload) {
  const data = payload?.data?.data;
  if (Array.isArray(data)) {
    return data
      .map((model) =>
        typeof model === 'string' ? model : String(model?.id || ''),
      )
      .filter(Boolean);
  }
  if (data && typeof data === 'object') {
    return Object.values(data)
      .flat()
      .map((model) => String(model || ''))
      .filter(Boolean);
  }
  return [];
}

function normalizeUserGroupMap(payload) {
  const rawData = payload?.data?.data;
  const normalized = {};

  if (Array.isArray(rawData)) {
    rawData.forEach((item, index) => {
      const groupName =
        typeof item === 'string'
          ? item.trim()
          : String(
              item?.name || item?.group || item?.value || item?.id || index,
            ).trim();
      if (!groupName) return;
      const info = typeof item === 'object' && item !== null ? item : {};
      normalized[groupName] = {
        ratio: info.ratio ?? 1,
        desc: info.desc || info.label || groupName,
      };
    });
  } else if (rawData && typeof rawData === 'object') {
    Object.entries(rawData).forEach(([groupName, info]) => {
      const normalizedGroup = String(groupName).trim();
      if (!normalizedGroup) return;
      if (info && typeof info === 'object') {
        normalized[normalizedGroup] = {
          ratio: info.ratio ?? 1,
          desc: info.desc || info.label || normalizedGroup,
        };
      } else {
        normalized[normalizedGroup] = {
          ratio: 1,
          desc: info == null ? normalizedGroup : String(info),
        };
      }
    });
  }

  return withNormalizedData(payload, normalized);
}

function normalizeDashboardGroupNames(payload) {
  const rawData = payload?.data?.data;
  let groupNames = [];
  if (Array.isArray(rawData)) {
    groupNames = rawData
      .map((item) =>
        typeof item === 'string'
          ? item.trim()
          : String(
              item?.name || item?.group || item?.value || item?.id || '',
            ).trim(),
      )
      .filter(Boolean);
  } else if (rawData && typeof rawData === 'object') {
    groupNames = Object.keys(rawData)
      .map((groupName) => String(groupName).trim())
      .filter(Boolean);
  }
  return withNormalizedData(payload, groupNames);
}

function normalizeUserModelNames(payload) {
  return withNormalizedData(payload, flattenDashboardModels(payload));
}

function normalizeChannelModelOptions(payload) {
  const modelNames = flattenDashboardModels(payload);
  return withNormalizedData(
    payload,
    modelNames.map((modelName) => ({ id: modelName })),
  );
}

function normalizeTokenQuotaCandidates(payload) {
  const rawData = payload?.data?.data;
  if (Array.isArray(rawData)) {
    return withNormalizedData(payload, { candidates: rawData });
  }
  if (
    rawData &&
    typeof rawData === 'object' &&
    !Array.isArray(rawData.candidates)
  ) {
    return withNormalizedData(payload, {
      ...(rawData || {}),
      candidates: Object.values(rawData).filter(
        (item) => item && typeof item === 'object',
      ),
    });
  }
  return payload;
}

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
      const response = await originalGet(url, {
        ...config,
        skipErrorHandler: true,
      });
      return normalizeChannelModelOptions(response);
    } catch (error) {
      if (error.response?.status !== 404) {
        throw error;
      }
      try {
        const fallback = await originalGet('/api/models', {
          ...config,
          skipErrorHandler: true,
        });
        const models = flattenDashboardModels(fallback.data).map((model) => ({
          id: model,
        }));
        return { data: { success: true, data: models } };
      } catch (fallbackError) {
        if (fallbackError.response?.status === 404) {
          return EMPTY_SUCCESS_RESPONSE;
        }
        throw fallbackError;
      }
    }
  }
  if (requestUrl.startsWith('/api/user/models')) {
    try {
      const response = await originalGet(url, {
        ...config,
        skipErrorHandler: true,
      });
      return normalizeUserModelNames(response);
    } catch (error) {
      if (error.response?.status !== 404) {
        throw error;
      }
      try {
        const fallback = await originalGet('/api/models', {
          ...config,
          skipErrorHandler: true,
        });
        return {
          data: { success: true, data: flattenDashboardModels(fallback.data) },
        };
      } catch (fallbackError) {
        if (fallbackError.response?.status === 404) {
          return EMPTY_SUCCESS_RESPONSE;
        }
        throw fallbackError;
      }
    }
  }
  if (requestUrl.startsWith('/api/user/self/groups')) {
    try {
      const response = await originalGet(url, {
        ...config,
        skipErrorHandler: true,
      });
      return normalizeUserGroupMap(response);
    } catch (error) {
      if (error.response?.status !== 404) {
        throw error;
      }
      try {
        return await originalGet('/api/user/groups', {
          ...config,
          skipErrorHandler: true,
        });
      } catch (fallbackError) {
        if (fallbackError.response?.status !== 404) {
          throw fallbackError;
        }
        try {
          const groups = await originalGet('/api/group/', {
            ...config,
            skipErrorHandler: true,
          });
          return normalizeUserGroupMap(groups);
        } catch (_) {
          return { data: { success: true, data: {} } };
        }
      }
    }
  }
  if (requestUrl.startsWith('/api/group/')) {
    try {
      const response = await originalGet(url, {
        ...config,
        skipErrorHandler: true,
      });
      return normalizeDashboardGroupNames(response);
    } catch (error) {
      if (error.response?.status !== 404) {
        throw error;
      }
      try {
        const groups = await originalGet('/api/user/self/groups', {
          ...config,
          skipErrorHandler: true,
        });
        const data = groups.data?.data || {};
        const groupNames =
          data && typeof data === 'object' && !Array.isArray(data)
            ? Object.keys(data)
            : Array.isArray(data)
              ? data.map((item) => String(item || '')).filter(Boolean)
              : [];
        return { data: { success: true, data: groupNames } };
      } catch (_) {
        return EMPTY_SUCCESS_RESPONSE;
      }
    }
  }
  if (requestUrl.startsWith('/api/token/model_quota_candidates')) {
    try {
      const response = await originalGet(url, {
        ...config,
        skipErrorHandler: true,
      });
      return normalizeTokenQuotaCandidates(response);
    } catch (error) {
      if (error.response?.status === 404) {
        return { data: { success: true, data: { candidates: [] } } };
      }
      throw error;
    }
  }
  if (requestUrl.startsWith('/api/token/model_quota_capabilities')) {
    try {
      return await originalGet(url, { ...config, skipErrorHandler: true });
    } catch (error) {
      if (error.response?.status === 404) {
        return { data: { success: true, data: {} } };
      }
      throw error;
    }
  }
  if (requestUrl.startsWith('/api/model_quota/')) {
    try {
      return await originalGet(url, { ...config, skipErrorHandler: true });
    } catch (error) {
      if (error.response?.status === 404) {
        return { data: { success: true, data: [] } };
      }
      throw error;
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

  const notifySubmitResult = (result) => {
    if (!result || typeof result !== 'object') return;
    window.parent?.postMessage(
      {
        type: 'na-platform-edit-result',
        status: result.status === 'success' ? 'success' : 'error',
        message: String(
          result.message ||
            (result.status === 'success' ? '保存成功' : '保存失败'),
        ),
      },
      '*',
    );
  };

  const handleClose = (result) => {
    setVisible(false);
    if (result) notifySubmitResult(result);
    window.parent?.postMessage(
      { type: 'na-platform-edit-close', changed: result?.status === 'success' },
      '*',
    );
  };

  const modalProps = {
    refresh: () => {},
    handleClose,
    visible,
    visiable: visible,
  };

  if (error) {
    return (
      <div className='platform-edit-state platform-edit-error'>{error}</div>
    );
  }
  if (!ready) {
    return (
      <div className='platform-edit-state platform-edit-loading'>
        正在加载编辑器...
      </div>
    );
  }
  return (
    <React.StrictMode>
      <StatusProvider>
        <LocaleProvider locale={zh_CN}>
          {kind === 'channels' ? (
            <EditChannelModal
              editingChannel={{ id: recordId }}
              {...modalProps}
            />
          ) : (
            <EditTokenModal editingToken={{ id: recordId }} {...modalProps} />
          )}
        </LocaleProvider>
      </StatusProvider>
    </React.StrictMode>
  );
};

ReactDOM.createRoot(document.getElementById('root')).render(
  <PlatformEditPage />,
);
