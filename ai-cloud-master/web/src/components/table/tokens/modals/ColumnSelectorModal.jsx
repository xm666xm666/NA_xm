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
import { Modal, Button, Checkbox } from '@douyinfe/semi-ui';

// ColumnSelectorModal 提供令牌表列显隐设置，并把模型限流列纳入统一配置。
const ColumnSelectorModal = ({
  showColumnSelector,
  setShowColumnSelector,
  visibleColumns,
  handleColumnVisibilityChange,
  handleSelectAll,
  initDefaultColumns,
  COLUMN_KEYS,
  t,
}) => {
  // 列定义保持静态，避免为了列设置弹窗重复构建整套表格 render 函数。
  const columnOptions = [
    { key: COLUMN_KEYS.NAME, title: t('名称') },
    { key: COLUMN_KEYS.STATUS, title: t('状态') },
    { key: COLUMN_KEYS.QUOTA_USAGE, title: t('剩余额度/总额度') },
    { key: COLUMN_KEYS.GROUP, title: t('分组') },
    { key: COLUMN_KEYS.TOKEN_KEY, title: t('密钥') },
    { key: COLUMN_KEYS.TOKEN_MODEL_LIMIT, title: t('可用模型') },
    // 将模型级限流状态纳入列设置，保持和表格展示能力一致。
    { key: COLUMN_KEYS.TOKEN_MODEL_RATE_LIMITS, title: t('模型限流') },
    { key: COLUMN_KEYS.ALLOW_IPS, title: t('IP限制') },
    { key: COLUMN_KEYS.CREATED_TIME, title: t('创建时间') },
    { key: COLUMN_KEYS.EXPIRED_TIME, title: t('过期时间') },
    { key: COLUMN_KEYS.OPERATE, title: t('操作') },
  ];

  return (
    <Modal
      title={t('列设置')}
      visible={showColumnSelector}
      onCancel={() => setShowColumnSelector(false)}
      footer={
        <div className='flex justify-end'>
          <Button onClick={() => initDefaultColumns()}>{t('重置')}</Button>
          <Button onClick={() => setShowColumnSelector(false)}>
            {t('取消')}
          </Button>
          <Button onClick={() => setShowColumnSelector(false)}>
            {t('确定')}
          </Button>
        </div>
      }
    >
      <div style={{ marginBottom: 20 }}>
        <Checkbox
          checked={Object.values(visibleColumns).every((value) => value === true)}
          indeterminate={
            Object.values(visibleColumns).some((value) => value === true) &&
            !Object.values(visibleColumns).every((value) => value === true)
          }
          onChange={(event) => handleSelectAll(event.target.checked)}
        >
          {t('全选')}
        </Checkbox>
      </div>
      <div
        className='flex flex-wrap max-h-96 overflow-y-auto rounded-lg p-4'
        style={{ border: '1px solid var(--semi-color-border)' }}
      >
        {columnOptions.map((column) => (
          <div key={column.key} className='w-1/2 mb-4 pr-2'>
            <Checkbox
              checked={!!visibleColumns[column.key]}
              onChange={(event) =>
                handleColumnVisibilityChange(column.key, event.target.checked)
              }
            >
              {column.title}
            </Checkbox>
          </div>
        ))}
      </div>
    </Modal>
  );
};

export default ColumnSelectorModal;
