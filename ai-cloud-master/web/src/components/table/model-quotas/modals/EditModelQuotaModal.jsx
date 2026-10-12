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

import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Avatar,
  Button,
  Card,
  Col,
  Form,
  Row,
  SideSheet,
  Space,
  Tag,
  Typography,
} from '@douyinfe/semi-ui';
import { Database, Save, X } from 'lucide-react';
import { useIsMobile } from '../../../../hooks/common/useIsMobile';
import { showError } from '../../../../helpers';

const { Text, Title } = Typography;

// 将数字字段统一转成接口期望的 number | null，避免空字符串污染请求体。
const normalizeOptionalNumber = (value) => {
  if (value === '' || value === undefined || value === null) {
    return null;
  }
  if (typeof value === 'number') {
    return Number.isNaN(value) ? null : value;
  }
  const parsed = Number(value);
  return Number.isNaN(parsed) ? null : parsed;
};

// 统一生成编辑弹窗初始值，保持普通项与共享池两种模式的数据结构一致。
const buildInitValues = (item, modalMode) => ({
  id: item?.id || 0,
  pool_id: item?.id || 0,
  pool_name: item?.quota_name || '',
  rpm: item?.rpm ?? null,
  tpm: item?.tpm ?? null,
  concurrency: item?.concurrency ?? null,
  member_ids:
    modalMode === 'shared_pool'
      ? (item?.children || []).map((child) => child.id)
      : [],
});

// sumAllocatedTokenRateLimits 汇总“令牌名 - 限流配置”列中的已分配额度，供前端保存前做最小一致性校验。
const sumAllocatedTokenRateLimits = (rateLimits = []) =>
  rateLimits.reduce(
    (accumulator, limit) => ({
      rpm: accumulator.rpm + (limit?.rpm_limit || 0),
      tpm: accumulator.tpm + (limit?.tpm_limit || 0),
      concurrency: accumulator.concurrency + (limit?.concurrency_limit || 0),
    }),
    { rpm: 0, tpm: 0, concurrency: 0 },
  );

// getAllocatedLimitsFromEditingItem 根据当前编辑对象计算已分配额度。
// 共享池项需要汇总全部子项，普通项只读取自身展示列。
const getAllocatedLimitsFromEditingItem = (item, modalMode) => {
  if (modalMode === 'shared_pool') {
    return (item?.children || []).reduce(
      (accumulator, child) => {
        const childAllocated = sumAllocatedTokenRateLimits(
          child?.token_rate_limits || [],
        );
        return {
          rpm: accumulator.rpm + childAllocated.rpm,
          tpm: accumulator.tpm + childAllocated.tpm,
          concurrency: accumulator.concurrency + childAllocated.concurrency,
        };
      },
      { rpm: 0, tpm: 0, concurrency: 0 },
    );
  }
  return sumAllocatedTokenRateLimits(item?.token_rate_limits || []);
};

// validateAllocatedTotalConsistency 在前端提前拦截会破坏已分配额度的总额度输入。
const validateAllocatedTotalConsistency = (payload, allocated, t) => {
  const dimensions = [
    {
      label: 'RPM',
      total: payload.rpm,
      allocated: allocated.rpm,
    },
    {
      label: 'TPM',
      total: payload.tpm,
      allocated: allocated.tpm,
    },
    {
      label: t('并发上限'),
      total: payload.concurrency,
      allocated: allocated.concurrency,
    },
  ];
  for (const dimension of dimensions) {
    if (
      (dimension.total === null || dimension.total === undefined) &&
      dimension.allocated > 0
    ) {
      showError(
        t('{{label}} 当前已分配 {{allocated}}，不能清空总额度', {
          label: dimension.label,
          allocated: dimension.allocated,
        }),
      );
      return false;
    }
    if (
      dimension.total !== null &&
      dimension.total !== undefined &&
      dimension.total < dimension.allocated
    ) {
      showError(
        t('{{label}} 当前已分配额度 {{allocated}} 已超过总额度 {{total}}', {
          label: dimension.label,
          allocated: dimension.allocated,
          total: dimension.total,
        }),
      );
      return false;
    }
  }
  return true;
};

// EditModelQuotaModal 复用同一张表单编辑普通模型项和共享配额池。
const EditModelQuotaModal = ({
  visible,
  modalMode,
  editingItem,
  memberOptions,
  onCancel,
  onSubmit,
  t,
}) => {
  const isMobile = useIsMobile();
  const [loading, setLoading] = useState(false);
  const formApiRef = useRef(null);
  const allocatedLimits = useMemo(
    () => getAllocatedLimitsFromEditingItem(editingItem, modalMode),
    [editingItem, modalMode],
  );

  const title = useMemo(
    () =>
      modalMode === 'shared_pool'
        ? editingItem?.id
          ? t('编辑共享池')
          : t('新建共享池')
        : t('编辑模型配额'),
    [editingItem?.id, modalMode, t],
  );

  const initValues = useMemo(
    () => buildInitValues(editingItem, modalMode),
    [editingItem, modalMode],
  );

  useEffect(() => {
    if (!visible) {
      formApiRef.current?.reset();
      setLoading(false);
      return;
    }
    formApiRef.current?.setValues(initValues);
  }, [initValues, visible]);

  const handleSubmit = async (values) => {
    setLoading(true);
    const payload =
      modalMode === 'shared_pool'
        ? {
            pool_id: values.pool_id || 0,
            pool_name: values.pool_name?.trim?.() || '',
            rpm: normalizeOptionalNumber(values.rpm),
            tpm: normalizeOptionalNumber(values.tpm),
            concurrency: normalizeOptionalNumber(values.concurrency),
            member_ids: Array.isArray(values.member_ids)
              ? values.member_ids
              : [],
          }
        : {
            id: values.id,
            rpm: normalizeOptionalNumber(values.rpm),
            tpm: normalizeOptionalNumber(values.tpm),
            concurrency: normalizeOptionalNumber(values.concurrency),
          };

    if (!validateAllocatedTotalConsistency(payload, allocatedLimits, t)) {
      setLoading(false);
      return;
    }

    const success = await onSubmit(payload);
    if (!success) {
      setLoading(false);
      return;
    }
    setLoading(false);
  };

  return (
    <SideSheet
      visible={visible}
      title={
        <Space>
          <Tag color={modalMode === 'shared_pool' ? 'purple' : 'blue'}>
            {modalMode === 'shared_pool' ? t('共享池') : t('普通项')}
          </Tag>
          <Title heading={4} className='m-0'>
            {title}
          </Title>
        </Space>
      }
      width={isMobile ? '100%' : 640}
      closeIcon={null}
      onCancel={onCancel}
      footer={
        <div className='flex justify-end bg-white'>
          <Space>
            <Button
              theme='solid'
              icon={<Save size={16} />}
              loading={loading}
              onClick={() => formApiRef.current?.submitForm()}
            >
              {t('保存')}
            </Button>
            <Button
              theme='light'
              type='primary'
              icon={<X size={16} />}
              onClick={onCancel}
            >
              {t('取消')}
            </Button>
          </Space>
        </div>
      }
    >
      <Form
        initValues={initValues}
        getFormApi={(api) => {
          formApiRef.current = api;
        }}
        onSubmit={handleSubmit}
      >
        <div className='p-2'>
          <Card className='!rounded-2xl shadow-sm border-0'>
            <div className='flex items-center mb-2'>
              <Avatar size='small' color='blue' className='mr-2 shadow-md'>
                <Database size={16} />
              </Avatar>
              <div>
                <Text className='text-lg font-medium'>{t('基础配置')}</Text>
                <div className='text-xs text-gray-600'>
                  {modalMode === 'shared_pool'
                    ? t('编辑共享池额度与成员模型')
                    : t('编辑普通模型项的额度配置')}
                </div>
              </div>
            </div>
            <Row gutter={12}>
              {modalMode === 'shared_pool' && (
                <>
                  <Col span={24}>
                    <Form.Input
                      field='pool_name'
                      label={t('共享池名称')}
                      placeholder={t('请输入共享池名称')}
                      rules={[
                        { required: true, message: t('请输入共享池名称') },
                      ]}
                      showClear
                    />
                  </Col>
                  <Col span={24}>
                    <Form.Select
                      field='member_ids'
                      label={t('成员模型')}
                      placeholder={t('请选择共享池成员')}
                      optionList={memberOptions}
                      multiple
                      search
                      rules={[
                        {
                          required: true,
                          message: t('请至少选择一个成员模型'),
                        },
                      ]}
                    />
                  </Col>
                </>
              )}
              <Col span={24}>
                <div className='rounded-xl border border-gray-100 bg-gray-50 px-3 py-3'>
                  <Text className='mb-3 block text-sm font-medium'>
                    {t('额度配置')}
                  </Text>
                  <div className='space-y-3'>
                    <Form.InputNumber
                      field='rpm'
                      label='RPM'
                      min={1}
                      step={1}
                      style={{ width: '100%' }}
                    />
                    <Form.InputNumber
                      field='tpm'
                      label='TPM'
                      min={1}
                      step={1}
                      style={{ width: '100%' }}
                    />
                    <Form.InputNumber
                      field='concurrency'
                      label={t('并发上限')}
                      min={1}
                      step={1}
                      style={{ width: '100%' }}
                    />
                  </div>
                </div>
              </Col>
            </Row>
          </Card>
        </div>
      </Form>
    </SideSheet>
  );
};

export default EditModelQuotaModal;
