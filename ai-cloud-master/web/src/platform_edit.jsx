import React, { useState } from 'react';
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

const [visible, setVisible] = React.useState(true);

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

ReactDOM.createRoot(document.getElementById('root')).render(
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
  </React.StrictMode>,
);
