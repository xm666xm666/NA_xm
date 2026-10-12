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
import { Modal } from '@douyinfe/semi-ui';

const ResetTwoFAModal = ({ visible, onCancel, onConfirm, user, t }) => {
  return (
    <Modal
      title={t('确认重置两步验证')}
      visible={visible}
      onCancel={onCancel}
      onOk={onConfirm}
      type='warning'
    >
      {t(
        '此操作将删除该用户当前的 MFA 密钥和备用码，用户下次登录时必须重新扫码绑定。',
      )}{' '}
      {user?.username
        ? t('目标用户：{{username}}', { username: user.username })
        : ''}
    </Modal>
  );
};

export default ResetTwoFAModal;
