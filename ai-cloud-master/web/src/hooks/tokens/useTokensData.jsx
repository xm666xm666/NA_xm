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

import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Modal } from '@douyinfe/semi-ui';
import {
  copy,
  showError,
  showSuccess,
  encodeToBase64,
} from '../../helpers';
import { ITEMS_PER_PAGE } from '../../constants';
import { useTableCompactMode } from '../common/useTableCompactMode';
import { TokenService } from '../../services/token';
import { emitTokenModelQuotaRefresh } from '../../helpers/tokenModelQuotaEvents';

export const useTokensData = (openFluentNotification) => {
  const { t } = useTranslation();

  // Basic state
  const [tokens, setTokens] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activePage, setActivePage] = useState(1);
  const [tokenCount, setTokenCount] = useState(0);
  const [pageSize, setPageSize] = useState(ITEMS_PER_PAGE);
  const [searching, setSearching] = useState(false);

  // Selection state
  const [selectedKeys, setSelectedKeys] = useState([]);

  // Edit state
  const [showEdit, setShowEdit] = useState(false);
  const [editingToken, setEditingToken] = useState({
    id: undefined,
  });

  // UI state
  const [compactMode, setCompactMode] = useTableCompactMode('tokens');
  const [showKeys, setShowKeys] = useState({});
  // 列可见性状态使用本地存储持久化，保持与其他表格页一致。
  const [visibleColumns, setVisibleColumns] = useState({});
  const [showColumnSelector, setShowColumnSelector] = useState(false);

  // 列 key 常量用于表格筛选与列设置弹窗复用。
  const COLUMN_KEYS = {
    NAME: 'name',
    STATUS: 'status',
    QUOTA_USAGE: 'quota_usage',
    GROUP: 'group',
    TOKEN_KEY: 'token_key',
    TOKEN_MODEL_LIMIT: 'token_model_limit',
    // 模型级限流标记单独成列，便于列表页快速识别已配置令牌。
    TOKEN_MODEL_RATE_LIMITS: 'token_model_rate_limits',
    ALLOW_IPS: 'allow_ips',
    CREATED_TIME: 'created_time',
    EXPIRED_TIME: 'expired_time',
    OPERATE: 'operate',
  };

  // Form state
  const [formApi, setFormApi] = useState(null);
  const formInitValues = {
    searchKeyword: '',
    searchToken: '',
  };

  // Get form values helper function
  const getFormValues = () => {
    const formValues = formApi ? formApi.getValues() : {};
    return {
      searchKeyword: formValues.searchKeyword || '',
      searchToken: formValues.searchToken || '',
    };
  };

  // Close edit modal
  const closeEdit = () => {
    setShowEdit(false);
    setTimeout(() => {
      setEditingToken({
        id: undefined,
      });
    }, 500);
  };

  // 令牌表默认展示全部核心列，便于首批功能不改变原有默认体验。
  const getDefaultColumnVisibility = () => {
    return {
      [COLUMN_KEYS.NAME]: true,
      [COLUMN_KEYS.STATUS]: true,
      [COLUMN_KEYS.QUOTA_USAGE]: true,
      [COLUMN_KEYS.GROUP]: true,
      [COLUMN_KEYS.TOKEN_KEY]: true,
      [COLUMN_KEYS.TOKEN_MODEL_LIMIT]: true,
      [COLUMN_KEYS.TOKEN_MODEL_RATE_LIMITS]: true,
      [COLUMN_KEYS.ALLOW_IPS]: true,
      [COLUMN_KEYS.CREATED_TIME]: true,
      [COLUMN_KEYS.EXPIRED_TIME]: true,
      [COLUMN_KEYS.OPERATE]: true,
    };
  };

  // 初始化默认列配置，并同步写入本地存储，避免首次打开为空。
  const initDefaultColumns = () => {
    const defaults = getDefaultColumnVisibility();
    setVisibleColumns(defaults);
    localStorage.setItem('tokens-table-columns', JSON.stringify(defaults));
  };

  // 列设置弹窗中的单列切换。
  const handleColumnVisibilityChange = (columnKey, checked) => {
    const updatedColumns = { ...visibleColumns, [columnKey]: checked };
    setVisibleColumns(updatedColumns);
  };

  // 支持一键全选/全不选列。
  const handleSelectAll = (checked) => {
    const updatedColumns = {};
    Object.values(COLUMN_KEYS).forEach((key) => {
      updatedColumns[key] = checked;
    });
    setVisibleColumns(updatedColumns);
  };

  // Sync page data from API response
  const syncPageData = (payload) => {
    setTokens(payload.items || []);
    setTokenCount(payload.total || 0);
    setActivePage(payload.page || 1);
    setPageSize(payload.page_size || pageSize);
  };

  // Load tokens function
  const loadTokens = async (page = 1, size = pageSize) => {
    setLoading(true);
    const { success, message, data } = await TokenService.getTokens(page, size);
    if (success) {
      syncPageData(data);
    } else {
      showError(message);
    }
    setLoading(false);
  };

  // Refresh function
  const refresh = async (page = activePage) => {
    await loadTokens(page);
    setSelectedKeys([]);
  };

  // Copy text function
  const copyText = async (text) => {
    if (await copy(text)) {
      showSuccess(t('已复制到剪贴板！'));
    } else {
      Modal.error({
        title: t('无法复制到剪贴板，请手动复制'),
        content: text,
        size: 'large',
      });
    }
  };

  // Open link function for chat integrations
  const onOpenLink = async (type, url, record) => {
    if (url && url.startsWith('fluent')) {
      openFluentNotification(record.key);
      return;
    }
    let status = localStorage.getItem('status');
    let serverAddress = '';
    if (status) {
      status = JSON.parse(status);
      serverAddress = status.server_address;
    }
    if (serverAddress === '') {
      serverAddress = window.location.origin;
    }
    if (url.includes('{cherryConfig}') === true) {
      let cherryConfig = {
        id: 'new-api',
        baseUrl: serverAddress,
        apiKey: 'sk-' + record.key,
      };
      let encodedConfig = encodeURIComponent(
        encodeToBase64(JSON.stringify(cherryConfig)),
      );
      url = url.replaceAll('{cherryConfig}', encodedConfig);
    } else {
      let encodedServerAddress = encodeURIComponent(serverAddress);
      url = url.replaceAll('{address}', encodedServerAddress);
      url = url.replaceAll('{key}', 'sk-' + record.key);
    }

    window.open(url, '_blank');
  };

  // Manage token function (delete, enable, disable)
  const manageToken = async (id, action, record) => {
    setLoading(true);
    let data = { id };
    let result;
    switch (action) {
      case 'delete':
        result = await TokenService.deleteToken(id);
        break;
      case 'enable':
        data.status = 1;
        result = await TokenService.updateTokenStatus(data);
        break;
      case 'disable':
        data.status = 2;
        result = await TokenService.updateTokenStatus(data);
        break;
    }
    const { success, message } = result;
    if (success) {
      showSuccess('操作成功完成！');
      // 删除令牌会回补模型配额并移除展示项，因此需要通知模型配额页同步刷新。
      if (action === 'delete') {
        emitTokenModelQuotaRefresh({ source: 'token-manage-delete' });
      }
      let token = result.data;
      let newTokens = [...tokens];
      if (action !== 'delete') {
        record.status = token.status;
      }
      setTokens(newTokens);
    } else {
      showError(message);
    }
    setLoading(false);
  };

  // Search tokens function
  const searchTokens = async () => {
    const { searchKeyword, searchToken } = getFormValues();
    if (searchKeyword === '' && searchToken === '') {
      await loadTokens(1);
      return;
    }
    setSearching(true);
    const { success, message, data } = await TokenService.searchTokens(
      searchKeyword,
      searchToken,
    );
    if (success) {
      setTokens(data);
      setTokenCount(data.length);
      setActivePage(1);
    } else {
      showError(message);
    }
    setSearching(false);
  };

  // Sort tokens function
  const sortToken = (key) => {
    if (tokens.length === 0) return;
    setLoading(true);
    let sortedTokens = [...tokens];
    sortedTokens.sort((a, b) => {
      return ('' + a[key]).localeCompare(b[key]);
    });
    if (sortedTokens[0].id === tokens[0].id) {
      sortedTokens.reverse();
    }
    setTokens(sortedTokens);
    setLoading(false);
  };

  // Page handlers
  const handlePageChange = (page) => {
    loadTokens(page, pageSize).then();
  };

  const handlePageSizeChange = async (size) => {
    setPageSize(size);
    await loadTokens(1, size);
  };

  // Row selection handlers
  const rowSelection = {
    onSelect: (record, selected) => {},
    onSelectAll: (selected, selectedRows) => {},
    onChange: (selectedRowKeys, selectedRows) => {
      setSelectedKeys(selectedRows);
    },
  };

  // Handle row styling
  const handleRow = (record, index) => {
    if (record.status !== 1) {
      return {
        style: {
          background: 'var(--semi-color-disabled-border)',
        },
      };
    } else {
      return {};
    }
  };

  // Batch delete tokens
  const batchDeleteTokens = async () => {
    if (selectedKeys.length === 0) {
      showError(t('请先选择要删除的令牌！'));
      return;
    }
    setLoading(true);
    try {
      const ids = selectedKeys.map((token) => token.id);
      const result = await TokenService.batchDeleteTokens(ids);
      if (result?.success) {
        const count = result.data || 0;
        showSuccess(t('已删除 {{count}} 个令牌！', { count }));
        // 批量删除会统一回补模型配额，通知模型配额页重拉最新结果。
        emitTokenModelQuotaRefresh({ source: 'token-batch-delete', count });
        await refresh();
        setTimeout(() => {
          if (tokens.length === 0 && activePage > 1) {
            refresh(activePage - 1);
          }
        }, 100);
      } else {
        showError(result?.message || t('删除失败'));
      }
    } catch (error) {
      showError(error.message);
    } finally {
      setLoading(false);
    }
  };

  // Batch copy tokens
  const batchCopyTokens = (copyType) => {
    if (selectedKeys.length === 0) {
      showError(t('请至少选择一个令牌！'));
      return;
    }

    Modal.info({
      title: t('复制令牌'),
      icon: null,
      content: t('请选择你的复制方式'),
      footer: (
        <div className='flex gap-2'>
          <button
            className='px-3 py-1 bg-gray-200 rounded'
            onClick={async () => {
              let content = '';
              for (let i = 0; i < selectedKeys.length; i++) {
                content +=
                  selectedKeys[i].name + '    sk-' + selectedKeys[i].key + '\n';
              }
              await copyText(content);
              Modal.destroyAll();
            }}
          >
            {t('名称+密钥')}
          </button>
          <button
            className='px-3 py-1 bg-blue-500 text-white rounded'
            onClick={async () => {
              let content = '';
              for (let i = 0; i < selectedKeys.length; i++) {
                content += 'sk-' + selectedKeys[i].key + '\n';
              }
              await copyText(content);
              Modal.destroyAll();
            }}
          >
            {t('仅密钥')}
          </button>
        </div>
      ),
    });
  };

  // Initialize data
  useEffect(() => {
    loadTokens(1)
      .then()
      .catch((reason) => {
        showError(reason);
      });
  }, [pageSize]);

  // 读取历史列配置时与默认值合并，兼容后续列扩展。
  useEffect(() => {
    const savedColumns = localStorage.getItem('tokens-table-columns');
    if (savedColumns) {
      try {
        const parsed = JSON.parse(savedColumns);
        const merged = { ...getDefaultColumnVisibility(), ...parsed };
        setVisibleColumns(merged);
      } catch (error) {
        console.error('Failed to parse token column preferences', error);
        initDefaultColumns();
      }
    } else {
      initDefaultColumns();
    }
  }, []);

  // 列设置发生变化后持久化，刷新页面仍保留用户偏好。
  useEffect(() => {
    if (Object.keys(visibleColumns).length > 0) {
      localStorage.setItem(
        'tokens-table-columns',
        JSON.stringify(visibleColumns),
      );
    }
  }, [visibleColumns]);

  return {
    // Basic state
    tokens,
    loading,
    activePage,
    tokenCount,
    pageSize,
    searching,

    // Selection state
    selectedKeys,
    setSelectedKeys,

    // Edit state
    showEdit,
    setShowEdit,
    editingToken,
    setEditingToken,
    closeEdit,

    // UI state
    compactMode,
    setCompactMode,
    showKeys,
    setShowKeys,
    visibleColumns,
    showColumnSelector,
    setShowColumnSelector,
    initDefaultColumns,
    handleColumnVisibilityChange,
    handleSelectAll,
    COLUMN_KEYS,

    // Form state
    formApi,
    setFormApi,
    formInitValues,
    getFormValues,

    // Functions
    loadTokens,
    refresh,
    copyText,
    onOpenLink,
    manageToken,
    searchTokens,
    sortToken,
    handlePageChange,
    handlePageSizeChange,
    rowSelection,
    handleRow,
    batchDeleteTokens,
    batchCopyTokens,
    syncPageData,

    // Translation
    t,
  };
};
