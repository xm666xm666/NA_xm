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

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { showError, showSuccess } from '../../helpers';
import modelQuotaService from '../../services/modelQuota';
import { Modal } from '@douyinfe/semi-ui';
import { TOKEN_MODEL_QUOTA_REFRESH_EVENT } from '../../helpers/tokenModelQuotaEvents';

const ITEM_TYPE_NORMAL = 'normal';
const ITEM_TYPE_SHARED_POOL = 'shared_pool';
const ITEM_TYPE_SHARED_POOL_MEMBER = 'shared_pool_member';

// 统一为表格补充 key，避免每个视图层重复处理。
const withRowKey = (items = []) =>
  items.map((item) => ({
    ...item,
    key: item.id,
    children: Array.isArray(item.children)
      ? item.children.map((child) => ({
          ...child,
          key: child.id,
        }))
      : [],
  }));

// 将普通项与共享池子项都整理成共享池成员候选，便于弹窗复用。
const flattenMemberCandidates = (items = []) => {
  const candidates = [];
  items.forEach((item) => {
    if (item.item_type === ITEM_TYPE_NORMAL) {
      candidates.push(item);
      return;
    }
    if (item.item_type === ITEM_TYPE_SHARED_POOL) {
      (item.children || []).forEach((child) => {
        candidates.push(child);
      });
    }
  });
  return candidates;
};

// findItemFromAllItems 优先从完整列表中回捞编辑对象，避免分组筛选后共享池子项不全。
const findItemFromAllItems = (items = [], targetItem) => {
  if (!targetItem?.id) {
    return targetItem;
  }
  for (const item of items) {
    if (item.id === targetItem.id) {
      return item;
    }
    for (const child of item.children || []) {
      if (child.id === targetItem.id) {
        return child;
      }
    }
  }
  return targetItem;
};

// useModelQuotaData 封装模型配额页的数据加载、筛选、编辑和删除流程。
export const useModelQuotaData = () => {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(true);
  const [items, setItems] = useState([]);
  const [allItems, setAllItems] = useState([]);
  const [groupOptions, setGroupOptions] = useState([]);
  const [selectedGroup, setSelectedGroup] = useState('');
  const [showEditModal, setShowEditModal] = useState(false);
  const [editingItem, setEditingItem] = useState(null);
  const [modalMode, setModalMode] = useState('quota');

  const loadGroups = useCallback(async () => {
    try {
      const result = await modelQuotaService.listGroups();
      if (!result?.success) {
        showError(result?.message || t('获取分组失败'));
        return;
      }
      const options = (result.data || []).map((group) => ({
        label: group || t('默认分组'),
        value: group,
      }));
      setGroupOptions(options);
    } catch (error) {
      showError(error.response?.data?.message || t('获取分组失败'));
    }
  }, [t]);

  const loadModelQuotas = useCallback(
    async (group = selectedGroup) => {
      setLoading(true);
      try {
        // 编辑共享池时需要完整成员候选，因此始终保留一份未过滤数据。
        const [allResult, filteredResult] = await Promise.all([
          modelQuotaService.list(''),
          group ? modelQuotaService.list(group) : Promise.resolve(null),
        ]);

        if (!allResult?.success) {
          showError(allResult?.message || t('获取模型配额失败'));
          setAllItems([]);
          setItems([]);
          return;
        }

        const nextAllItems = withRowKey(
          modelQuotaService.extractArrayData(allResult.data),
        );
        setAllItems(nextAllItems);

        if (!group) {
          setItems(nextAllItems);
          return;
        }

        if (!filteredResult?.success) {
          showError(filteredResult?.message || t('获取模型配额失败'));
          setItems([]);
          return;
        }

        setItems(
          withRowKey(modelQuotaService.extractArrayData(filteredResult.data)),
        );
      } catch (error) {
        showError(error.response?.data?.message || t('获取模型配额失败'));
        setAllItems([]);
        setItems([]);
      } finally {
        setLoading(false);
      }
    },
    [selectedGroup, t],
  );

  useEffect(() => {
    loadGroups();
  }, [loadGroups]);

  useEffect(() => {
    loadModelQuotas(selectedGroup);
  }, [loadModelQuotas, selectedGroup]);

  useEffect(() => {
    const handleTokenModelQuotaRefresh = () => {
      // 令牌页变更限流配置后，模型配额页需要同步刷新剩余额度与展示列。
      loadModelQuotas(selectedGroup);
    };

    window.addEventListener(
      TOKEN_MODEL_QUOTA_REFRESH_EVENT,
      handleTokenModelQuotaRefresh,
    );
    return () => {
      window.removeEventListener(
        TOKEN_MODEL_QUOTA_REFRESH_EVENT,
        handleTokenModelQuotaRefresh,
      );
    };
  }, [loadModelQuotas, selectedGroup]);

  const normalItems = useMemo(
    () =>
      items.filter((item) => item.item_type === ITEM_TYPE_NORMAL).map((item) => ({
        ...item,
        children: undefined,
      })),
    [items],
  );

  const sharedPoolItems = useMemo(
    () => items.filter((item) => item.item_type === ITEM_TYPE_SHARED_POOL),
    [items],
  );

  const memberOptions = useMemo(
    () =>
      flattenMemberCandidates(allItems)
        .filter((item) => item.item_type !== ITEM_TYPE_SHARED_POOL)
        .map((item) => ({
          label: `${item.group || t('默认分组')} / ${item.model_name || item.quota_name}`,
          value: item.id,
          disabled: item.item_type === ITEM_TYPE_SHARED_POOL,
        })),
    [allItems, t],
  );

  const openQuotaEditor = useCallback(
    (item) => {
      setModalMode('quota');
      setEditingItem(findItemFromAllItems(allItems, item));
      setShowEditModal(true);
    },
    [allItems],
  );

  const openSharedPoolEditor = useCallback(
    (item) => {
      setModalMode('shared_pool');
      setEditingItem(findItemFromAllItems(allItems, item));
      setShowEditModal(true);
    },
    [allItems],
  );

  const openCreateSharedPool = useCallback(() => {
    setModalMode('shared_pool');
    setEditingItem({
      id: 0,
      item_type: ITEM_TYPE_SHARED_POOL,
      quota_name: '',
      member_ids: [],
      children: [],
      rpm: null,
      tpm: null,
      concurrency: null,
      remain_rpm: null,
      remain_tpm: null,
      remain_concurrency: null,
      is_available: true,
    });
    setShowEditModal(true);
  }, []);

  const closeEditModal = useCallback(() => {
    setShowEditModal(false);
    setEditingItem(null);
  }, []);

  const deleteItem = useCallback(
    async (item, actionType) => {
      try {
        const referenceResult = await modelQuotaService.getReferences(item.id);
        if (!referenceResult?.success) {
          showError(referenceResult?.message || t('获取引用令牌失败'));
          return false;
        }
        const tokenNames = referenceResult?.data?.token_names || [];
        const actionLabel =
          actionType === 'shared_pool'
            ? t('删除共享池')
            : actionType === 'member'
              ? t('移出共享池')
              : t('删除模型配额');
        const contentText =
          tokenNames.length > 0
            ? t('有令牌在使用，不能执行该操作：{{tokens}}', {
                tokens: tokenNames.join('、'),
              })
            : t('此操作不可撤销，确认继续吗？');
        Modal.confirm({
          title: actionLabel,
          content: contentText,
          okText: tokenNames.length > 0 ? t('知道了') : t('确认'),
          cancelText: tokenNames.length > 0 ? t('关闭') : t('取消'),
          okButtonProps: { disabled: tokenNames.length > 0 },
          onOk: async () => {
            if (tokenNames.length > 0) {
              return;
            }
            let result;
            if (actionType === 'shared_pool') {
              result = await modelQuotaService.deleteSharedPool(item.id);
            } else if (actionType === 'member') {
              result = await modelQuotaService.removeSharedPoolTag(item.id);
            } else {
              result = await modelQuotaService.deleteQuota(item.id);
            }
            if (!result?.success) {
              showError(result?.message || t('删除失败'));
              return;
            }
            showSuccess(
              actionType === 'shared_pool'
                ? t('共享池删除成功')
                : actionType === 'member'
                  ? t('已移出共享池')
                  : t('模型配额删除成功'),
            );
            await loadModelQuotas(selectedGroup);
          },
        });
        return true;
      } catch (error) {
        showError(error.response?.data?.message || t('删除失败'));
        return false;
      }
    },
    [loadModelQuotas, selectedGroup, t],
  );

  const submitEdit = useCallback(
    async (values) => {
      try {
        let result;
        if (modalMode === 'shared_pool') {
          result = await modelQuotaService.saveSharedPool(values);
        } else {
          result = await modelQuotaService.updateQuota(values);
        }

        if (!result?.success) {
          showError(result?.message || t('保存失败'));
          return false;
        }

        showSuccess(
          modalMode === 'shared_pool'
            ? t('共享池保存成功')
            : t('模型配额保存成功'),
        );
        closeEditModal();
        await loadModelQuotas(selectedGroup);
        return true;
      } catch (error) {
        showError(error.response?.data?.message || t('保存失败'));
        return false;
      }
    },
    [closeEditModal, loadModelQuotas, modalMode, selectedGroup, t],
  );

  return {
    t,
    loading,
    items,
    allItems,
    normalItems,
    sharedPoolItems,
    memberOptions,
    groupOptions,
    selectedGroup,
    setSelectedGroup,
    showEditModal,
    editingItem,
    modalMode,
    loadModelQuotas,
    refresh: loadModelQuotas,
    openQuotaEditor,
    openSharedPoolEditor,
    openCreateSharedPool,
    deleteItem,
    closeEditModal,
    submitEdit,
    ITEM_TYPE_NORMAL,
    ITEM_TYPE_SHARED_POOL,
    ITEM_TYPE_SHARED_POOL_MEMBER,
  };
};

export default useModelQuotaData;
