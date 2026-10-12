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

import { API, showError, showSuccess, showWarning } from '../../helpers';
import {
  Button,
  Card,
  Divider,
  Input,
  Modal,
  Spin,
  Steps,
  Typography,
} from '@douyinfe/semi-ui';
import { IconCopy, IconShield } from '@douyinfe/semi-icons';
import { QRCodeSVG } from 'qrcode.react';
import React, { useCallback, useEffect, useState } from 'react';
import { completeMFASetup, requestMFASetup } from './mfaSetupRequest';

const { Text, Paragraph } = Typography;
const LAST_SETUP_STEP = 2;

// BackupCodesDisplay 沿用原启用弹窗的备用码展示和整组复制入口。
const BackupCodesDisplay = ({ codes, title, onCopy, t }) => (
  <Card className='!rounded-xl' style={{ width: '100%' }}>
    <div className='space-y-3'>
      <div className='flex items-center justify-between'>
        <Text strong className='text-slate-700 dark:text-slate-200'>
          {title}
        </Text>
      </div>

      <div className='grid grid-cols-1 sm:grid-cols-2 gap-2'>
        {codes.map((code, index) => (
          <div key={code} className='rounded-lg p-3'>
            <div className='flex items-center justify-between'>
              <Text
                code
                className='text-sm font-mono text-slate-700 dark:text-slate-200'
              >
                {code}
              </Text>
              <Text type='quaternary' className='text-xs'>
                #{(index + 1).toString().padStart(2, '0')}
              </Text>
            </div>
          </div>
        ))}
      </div>

      <Divider margin={12} />
      <Button
        type='primary'
        theme='solid'
        icon={<IconCopy />}
        onClick={onCopy}
        className='!rounded-lg !bg-slate-600 hover:!bg-slate-700 w-full'
      >
        {t('复制所有代码')}
      </Button>
    </div>
  </Card>
);

const TwoFASetupModal = ({ visible, setupKey, onSuccess, onCancel, t }) => {
  const [loading, setLoading] = useState(false);
  const [setupLoading, setSetupLoading] = useState(false);
  const [setupData, setSetupData] = useState(null);
  const [setupError, setSetupError] = useState('');
  const [verificationCode, setVerificationCode] = useState('');
  const [currentStep, setCurrentStep] = useState(0);

  // requestSetup 按用户复用初始化请求，避免 StrictMode 重挂载生成两套密钥。
  const requestSetup = useCallback(async () => {
    if (!visible || !setupKey) {
      return;
    }

    setSetupLoading(true);
    setSetupError('');
    try {
      const response = await requestMFASetup(setupKey, () =>
        API.post('/api/user/2fa/setup'),
      );
      if (!response.data.success) {
        throw new Error(response.data.message);
      }
      setSetupData(response.data.data);
      setCurrentStep(0);
    } catch (error) {
      const message = error.message || '设置2FA失败';
      setSetupError(message);
      showError(message);
    } finally {
      setSetupLoading(false);
    }
  }, [setupKey, visible]);

  useEffect(() => {
    if (visible) {
      requestSetup();
      return;
    }

    // 退出强制绑定时清理一次性密钥，重新登录后必须重新获取绑定信息。
    setSetupData(null);
    setSetupError('');
    setVerificationCode('');
    setCurrentStep(0);
  }, [requestSetup, visible]);

  // copyBackupCodes 保留原弹窗的一键复制行为。
  const copyBackupCodes = async () => {
    try {
      await navigator.clipboard.writeText(setupData.backup_codes.join('\n'));
      showSuccess(t('备用码已复制到剪贴板'));
    } catch (error) {
      showError(t('复制失败，请手动复制'));
    }
  };

  // handleEnable 使用原 enable 接口，并将成功结果交给登录流程创建前端登录态。
  const handleEnable = async () => {
    if (!/^\d{6}$/.test(verificationCode)) {
      showWarning(t('请输入6位数字验证码'));
      return;
    }

    setLoading(true);
    try {
      const user = await completeMFASetup(
        (payload) => API.post('/api/user/2fa/enable', payload),
        verificationCode,
      );
      onSuccess?.(user);
    } catch (error) {
      showError(error.message || t('启用2FA失败'));
    } finally {
      setLoading(false);
    }
  };

  const handleCancel = () => {
    setSetupData(null);
    setSetupError('');
    setVerificationCode('');
    setCurrentStep(0);
    onCancel?.();
  };

  // renderFooter 沿用原三步弹窗的上一步、下一步和完成设置操作。
  const renderFooter = () => {
    if (!setupData) {
      return (
        <>
          <Button onClick={handleCancel}>{t('返回登录')}</Button>
          {setupError && (
            <Button
              type='primary'
              loading={setupLoading}
              onClick={requestSetup}
            >
              {t('重新加载')}
            </Button>
          )}
        </>
      );
    }

    return (
      <>
        {currentStep > 0 && (
          <Button
            onClick={() => setCurrentStep((step) => step - 1)}
            className='!rounded-lg'
          >
            {t('上一步')}
          </Button>
        )}
        {currentStep < LAST_SETUP_STEP ? (
          <Button
            type='primary'
            theme='solid'
            onClick={() => setCurrentStep((step) => step + 1)}
            className='!rounded-lg !bg-slate-600 hover:!bg-slate-700'
          >
            {t('下一步')}
          </Button>
        ) : (
          <Button
            type='primary'
            theme='solid'
            loading={loading}
            onClick={handleEnable}
            className='!rounded-lg !bg-slate-600 hover:!bg-slate-700'
          >
            {t('完成设置并启用两步验证')}
          </Button>
        )}
      </>
    );
  };

  return (
    <Modal
      title={
        <div className='flex items-center'>
          <IconShield className='mr-2 text-slate-600' />
          {t('设置两步验证')}
        </div>
      }
      visible={visible}
      onCancel={handleCancel}
      footer={renderFooter()}
      width={650}
      style={{ maxWidth: '90vw' }}
    >
      {setupLoading && !setupData ? (
        <div className='flex flex-col items-center gap-3 py-10'>
          {/* 提示文字独立于 Spin，避免被加载图标的固定宽度逐字换行。 */}
          <Spin />
          <Text type='secondary'>{t('正在生成 MFA 绑定信息...')}</Text>
        </div>
      ) : setupData ? (
        <div className='space-y-6'>
          {/* 步骤、文案和布局保持原启用弹窗一致。 */}
          <Steps type='basic' size='small' current={currentStep}>
            <Steps.Step
              title={t('扫描二维码')}
              description={t('使用认证器应用扫描二维码')}
            />
            <Steps.Step
              title={t('保存备用码')}
              description={t('保存备用码以备不时之需')}
            />
            <Steps.Step
              title={t('验证设置')}
              description={t('输入验证码完成设置')}
            />
          </Steps>

          <div className='rounded-xl'>
            {currentStep === 0 && (
              <div>
                <Paragraph className='text-gray-600 dark:text-gray-300 mb-4'>
                  {t(
                    '使用认证器应用（如 Google Authenticator、Microsoft Authenticator）扫描下方二维码：',
                  )}
                </Paragraph>
                <div className='flex justify-center mb-4'>
                  <div className='bg-white p-4 rounded-lg shadow-sm'>
                    <QRCodeSVG
                      value={setupData.qr_code_data}
                      size={180}
                      title={t('MFA 绑定二维码')}
                    />
                  </div>
                </div>
                <div className='bg-blue-50 dark:bg-blue-900 rounded-lg p-3'>
                  <Text className='text-blue-800 dark:text-blue-200 text-sm'>
                    {t('或手动输入密钥：')}
                    <Text code copyable className='ml-2'>
                      {setupData.secret}
                    </Text>
                  </Text>
                </div>
              </div>
            )}

            {currentStep === 1 && (
              <BackupCodesDisplay
                codes={setupData.backup_codes}
                title={t('备用恢复代码')}
                onCopy={copyBackupCodes}
                t={t}
              />
            )}

            {currentStep === LAST_SETUP_STEP && (
              <Input
                placeholder={t('输入认证器应用显示的6位数字验证码')}
                value={verificationCode}
                onChange={setVerificationCode}
                size='large'
                maxLength={6}
                className='!rounded-lg'
              />
            )}
          </div>
        </div>
      ) : (
        <div className='py-8 text-center'>
          <Text type='secondary'>{setupError}</Text>
        </div>
      )}
    </Modal>
  );
};

export default TwoFASetupModal;
