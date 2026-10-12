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

import React from 'react';
import { Button, Select, Space, Typography } from '@douyinfe/semi-ui';
import CardPro from '../../common/ui/CardPro';
import ModelQuotaTable from './ModelQuotaTable';
import EditModelQuotaModal from './modals/EditModelQuotaModal';
import { useModelQuotaData } from '../../../hooks/model-quotas/useModelQuotaData';

const { Text } = Typography;

// ModelQuotaPage 组合筛选、操作按钮、普通项表格和共享池表格。
const ModelQuotaPage = () => {
  const modelQuotaData = useModelQuotaData();
  const {
    t,
    loading,
    normalItems,
    sharedPoolItems,
    groupOptions,
    selectedGroup,
    setSelectedGroup,
    showEditModal,
    editingItem,
    modalMode,
    memberOptions,
    refresh,
    openQuotaEditor,
    openSharedPoolEditor,
    openCreateSharedPool,
    deleteItem,
    closeEditModal,
    submitEdit,
  } = modelQuotaData;

  return (
    <>
      <EditModelQuotaModal
        visible={showEditModal}
        modalMode={modalMode}
        editingItem={editingItem}
        memberOptions={memberOptions}
        onCancel={closeEditModal}
        onSubmit={submitEdit}
        t={t}
      />

      <CardPro
        type='type3'
        descriptionArea={
          <Space vertical align='start' spacing='tight'>
            <Text strong>{t('模型配额')}</Text>
            <Text type='secondary'>
              {t('首批支持普通项、共享池与共享池子项的基础查看和编辑。')}
            </Text>
          </Space>
        }
        actionsArea={
          <div className='flex flex-col md:flex-row justify-between items-center gap-2 w-full'>
            <Space wrap>
              <Button type='primary' theme='solid' onClick={openCreateSharedPool}>
                {t('新建共享池')}
              </Button>
              <Button theme='light' type='primary' onClick={() => refresh()}>
                {t('刷新')}
              </Button>
            </Space>
            <div className='w-full md:w-[260px]'>
              <Select
                value={selectedGroup}
                onChange={(value) => setSelectedGroup(value || '')}
                optionList={[
                  { label: t('全部分组'), value: '' },
                  ...groupOptions,
                ]}
                placeholder={t('按分组筛选')}
                showClear
                style={{ width: '100%' }}
              />
            </div>
          </div>
        }
        t={t}
      >
        <div className='flex flex-col gap-6'>
          <ModelQuotaTable
            title={t('普通项')}
            dataSource={normalItems}
            loading={loading}
            showGroup={true}
            type='normal'
            onEdit={openQuotaEditor}
            onDelete={(item) => deleteItem(item, 'normal')}
            onRemoveTag={() => {}}
            t={t}
          />
          <ModelQuotaTable
            title={t('共享池')}
            dataSource={sharedPoolItems}
            loading={loading}
            showGroup={false}
            type='shared_pool'
            onEdit={openSharedPoolEditor}
            onDelete={(item) => deleteItem(item, 'shared_pool')}
            onRemoveTag={(item) => deleteItem(item, 'member')}
            t={t}
          />
        </div>
      </CardPro>
    </>
  );
};

export default ModelQuotaPage;
