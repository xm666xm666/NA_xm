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

import React, { useMemo } from 'react';
import { Button, Empty, Space, Tag, Typography } from '@douyinfe/semi-ui';
import {
  IllustrationNoResult,
  IllustrationNoResultDark,
} from '@douyinfe/semi-illustrations';
import CardTable from '../../common/ui/CardTable';
import { renderGroup } from '../../../helpers';

const { Text } = Typography;

// 将空值统一显示为短横线，减少表格中的条件分支。
const renderNullableNumber = (value) => {
  if (value === null || value === undefined) {
    return <Text type='tertiary'>-</Text>;
  }
  return value;
};

// 统一渲染可用状态标签，避免普通项、共享池、子项各自重复定义。
const renderAvailability = (value, t) =>
  value ? <Tag color='green'>{t('可用')}</Tag> : <Tag color='red'>{t('不可用')}</Tag>;

// renderTokenRateLimits 统一渲染“令牌名 - 限流配置”列，便于普通项与子项共用。
const renderTokenRateLimits = (limits = [], t) => {
  if (!Array.isArray(limits) || limits.length === 0) {
    return <Text type='tertiary'>-</Text>;
  }

  return (
    <Space vertical align='start' spacing={4}>
      {limits.map((item, index) => {
        const limitParts = [];
        if (item.concurrency_limit !== null && item.concurrency_limit !== undefined) {
          limitParts.push(`${t('并发')} ${item.concurrency_limit}`);
        }
        if (item.rpm_limit !== null && item.rpm_limit !== undefined) {
          limitParts.push(`RPM ${item.rpm_limit}`);
        }
        if (item.tpm_limit !== null && item.tpm_limit !== undefined) {
          limitParts.push(`TPM ${item.tpm_limit}`);
        }
        return (
          <div key={`${item.token_id || 'token'}-${index}`} className='flex flex-col gap-1'>
            <Text size='small' strong>
              {item.token_name || t('未命名令牌')}
            </Text>
            <Text type='secondary' size='small'>
              {limitParts.length > 0 ? limitParts.join(' / ') : t('未配置限流')}
            </Text>
          </div>
        );
      })}
    </Space>
  );
};

// getColumns 按普通项、共享池、共享池子项三种展示场景生成表格列。
const getColumns = ({
  t,
  showGroup = true,
  onEdit,
  onDelete,
  onRemoveTag,
  type,
  showTokenRateLimits = false,
}) => {
  const columns = [
    {
      title: t('名称'),
      dataIndex: 'quota_name',
      key: 'quota_name',
      render: (text, record) => (
        <div className='flex flex-col'>
          <Text strong>{text || '-'}</Text>
          {record.model_name ? (
            <Text type='secondary' size='small'>
              {record.model_name}
            </Text>
          ) : null}
        </div>
      ),
    },
  ];

  if (showGroup) {
    columns.push({
      title: t('分组'),
      dataIndex: 'group',
      key: 'group',
      render: (text) => renderGroup(text || ''),
    });
  }

  if (showTokenRateLimits) {
    columns.push({
      title: t('令牌名 - 限流配置'),
      dataIndex: 'token_rate_limits',
      key: 'token_rate_limits',
      render: (value) => renderTokenRateLimits(value, t),
    });
  }

  // 共享池子项只保留只读身份与“令牌名 - 限流配置”列，不再展示额度账本字段。
  if (type === 'member') {
    columns.push(
      {
        title: t('状态'),
        dataIndex: 'is_available',
        key: 'is_available',
        render: (value) => renderAvailability(value, t),
      },
      {
        title: t('操作'),
        key: 'action',
        render: (_, record) => (
          <Space>
            <Button size='small' type='primary' theme='light' disabled>
              {t('子项只读')}
            </Button>
            <Button
              size='small'
              type='danger'
              theme='light'
              onClick={() => onRemoveTag?.(record)}
            >
              {t('移出共享池')}
            </Button>
          </Space>
        ),
      },
    );
    return columns;
  }

  columns.push(
    {
      title: 'RPM',
      dataIndex: 'rpm',
      key: 'rpm',
      render: renderNullableNumber,
    },
    {
      title: 'TPM',
      dataIndex: 'tpm',
      key: 'tpm',
      render: renderNullableNumber,
    },
    {
      title: t('并发'),
      dataIndex: 'concurrency',
      key: 'concurrency',
      render: renderNullableNumber,
    },
    {
      title: t('剩余 RPM'),
      dataIndex: 'remain_rpm',
      key: 'remain_rpm',
      render: renderNullableNumber,
    },
    {
      title: t('剩余 TPM'),
      dataIndex: 'remain_tpm',
      key: 'remain_tpm',
      render: renderNullableNumber,
    },
    {
      title: t('剩余并发'),
      dataIndex: 'remain_concurrency',
      key: 'remain_concurrency',
      render: renderNullableNumber,
    },
    {
      title: t('状态'),
      dataIndex: 'is_available',
      key: 'is_available',
      render: (value) => renderAvailability(value, t),
    },
    {
      title: t('操作'),
      key: 'action',
      render: (_, record) => (
        <Space>
          <Button
            size='small'
            type='primary'
            theme='light'
            disabled={type === 'member'}
            onClick={() => onEdit(record)}
          >
            {type === 'member' ? t('子项只读') : t('编辑')}
          </Button>
          <Button
            size='small'
            type='danger'
            theme='light'
            onClick={() => onDelete?.(record)}
          >
            {type === 'shared_pool' ? t('删除共享池') : t('删除')}
          </Button>
        </Space>
      ),
    },
  );

  return columns;
};

// sharedPoolExpandedRowRender 在共享池展开行中渲染只读子项表格。
const sharedPoolExpandedRowRender = (record, { t, onRemoveTag }) => {
  const childColumns = getColumns({
    t,
    showGroup: true,
    onEdit: () => {},
    onDelete: () => {},
    onRemoveTag,
    type: 'member',
    showTokenRateLimits: true,
  });

  return (
    <CardTable
      columns={childColumns}
      dataSource={record.memberItems || []}
      rowKey='key'
      hidePagination={true}
    />
  );
};

// ModelQuotaTable 统一承载普通项表格和共享池表格的渲染差异。
const ModelQuotaTable = ({
  title,
  dataSource,
  loading,
  t,
  showGroup = true,
  type = 'normal',
  onEdit,
  onDelete,
  onRemoveTag,
}) => {
  const columns = useMemo(
    () =>
      getColumns({
        t,
        showGroup,
        onEdit,
        onDelete,
        onRemoveTag,
        type,
        showTokenRateLimits: type === 'normal',
      }),
    [onDelete, onEdit, onRemoveTag, showGroup, t, type],
  );

  const tableDataSource = useMemo(() => {
    if (type !== 'shared_pool') {
      return dataSource;
    }

    // 共享池只保留展开子表这一种子项展示方式，避免主表原生 children 再重复渲染一遍。
    return dataSource.map((item) => ({
      ...item,
      memberItems: item.children || [],
      children: undefined,
    }));
  }, [dataSource, type]);

  return (
    <div className='flex flex-col gap-3'>
      <div className='flex items-center justify-between'>
        <Text strong>{title}</Text>
        <Text type='secondary' size='small'>
          {t('共 {{count}} 项', { count: dataSource.length })}
        </Text>
      </div>
      <CardTable
        columns={columns}
        dataSource={tableDataSource}
        loading={loading}
        rowKey='key'
        hidePagination={true}
        expandAllRows={false}
        expandedRowRender={
          type === 'shared_pool'
            ? (record) => sharedPoolExpandedRowRender(record, { t, onRemoveTag })
            : undefined
        }
        rowExpandable={
          type === 'shared_pool'
            ? (record) => Array.isArray(record.memberItems) && record.memberItems.length > 0
            : undefined
        }
        empty={
          <Empty
            image={<IllustrationNoResult style={{ width: 150, height: 150 }} />}
            darkModeImage={
              <IllustrationNoResultDark style={{ width: 150, height: 150 }} />
            }
            description={t('暂无数据')}
            style={{ padding: 30 }}
          />
        }
      />
      {type === 'shared_pool' && dataSource.length > 0 ? (
        <Space vertical spacing='tight'>
          <Text type='secondary' size='small'>
            {t('共享池可展开查看子项模型及其令牌名 - 限流配置。')}
          </Text>
        </Space>
      ) : null}
    </div>
  );
};

export default ModelQuotaTable;
