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
import { Input, Modal, Typography } from '@douyinfe/semi-ui';
import { IconLock } from '@douyinfe/semi-icons';
import Turnstile from 'react-turnstile';

const ChangePasswordModal = ({
  t,
  showChangePasswordModal,
  setShowChangePasswordModal,
  inputs,
  handleInputChange,
  changePassword,
  newPasswordError,
  passwordConfirmationError,
  turnstileEnabled,
  turnstileSiteKey,
  setTurnstileToken,
}) => {
  return (
    <Modal
      title={
        <div className='flex items-center'>
          <IconLock className='mr-2 text-orange-500' />
          {t('修改密码')}
        </div>
      }
      visible={showChangePasswordModal}
      onCancel={() => setShowChangePasswordModal(false)}
      onOk={changePassword}
      size={'small'}
      centered={true}
      className='modern-modal'
    >
      <div className='space-y-4 py-4'>
        <div>
          <Typography.Text strong className='block mb-2'>
            {t('原密码')}
          </Typography.Text>
          <Input
            name='original_password'
            placeholder={t('请输入原密码')}
            type='password'
            value={inputs.original_password}
            onChange={(value) => handleInputChange('original_password', value)}
            size='large'
            className='!rounded-lg'
            prefix={<IconLock />}
          />
        </div>

        <div>
          <Typography.Text strong className='block mb-2'>
            {t('新密码')}
          </Typography.Text>
          <Input
            name='set_new_password'
            placeholder={t(
              '8–20 位，必须包含大写字母、小写字母、数字、特殊符号中的至少三类',
            )}
            type='password'
            value={inputs.set_new_password}
            onChange={(value) => handleInputChange('set_new_password', value)}
            aria-invalid={Boolean(newPasswordError)}
            aria-describedby={
              newPasswordError ? 'new-password-error' : undefined
            }
            size='large'
            className='!rounded-lg'
            prefix={<IconLock />}
          />
          {/* 密码策略错误紧邻新密码输入框显示。 */}
          {newPasswordError && (
            <div
              id='new-password-error'
              role='alert'
              className='mt-1 text-xs text-red-500'
            >
              {newPasswordError}
            </div>
          )}
        </div>

        <div>
          <Typography.Text strong className='block mb-2'>
            {t('确认新密码')}
          </Typography.Text>
          <Input
            name='set_new_password_confirmation'
            placeholder={t('请再次输入新密码')}
            type='password'
            value={inputs.set_new_password_confirmation}
            onChange={(value) =>
              handleInputChange('set_new_password_confirmation', value)
            }
            aria-invalid={Boolean(passwordConfirmationError)}
            aria-describedby={
              passwordConfirmationError
                ? 'password-confirmation-error'
                : undefined
            }
            size='large'
            className='!rounded-lg'
            prefix={<IconLock />}
          />
          {/* 两次密码不一致时在确认输入框下方给出反馈。 */}
          {passwordConfirmationError && (
            <div
              id='password-confirmation-error'
              role='alert'
              className='mt-1 text-xs text-red-500'
            >
              {passwordConfirmationError}
            </div>
          )}
        </div>

        {turnstileEnabled && (
          <div className='flex justify-center'>
            <Turnstile
              sitekey={turnstileSiteKey}
              onVerify={(token) => {
                setTurnstileToken(token);
              }}
            />
          </div>
        )}
      </div>
    </Modal>
  );
};

export default ChangePasswordModal;
