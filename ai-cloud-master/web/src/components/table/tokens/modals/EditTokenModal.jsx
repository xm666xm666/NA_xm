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

import React, { useEffect, useState, useContext, useRef, useMemo } from 'react';
import {
  showError,
  showSuccess,
  timestamp2string,
  renderGroupOption,
  renderQuotaWithPrompt,
  getModelCategories,
  selectFilter,
} from '../../../../helpers';
import { emitTokenModelQuotaRefresh } from '../../../../helpers/tokenModelQuotaEvents';
import { useIsMobile } from '../../../../hooks/common/useIsMobile';
import {
  Button,
  SideSheet,
  Space,
  Spin,
  Typography,
  Card,
  Tag,
  Avatar,
  Form,
  Col,
  Row,
  Select as SemiSelect,
  InputNumber as SemiInputNumber,
  Switch as SemiSwitch,
  Modal,
} from '@douyinfe/semi-ui';
import {
  IconCreditCard,
  IconLink,
  IconSave,
  IconClose,
  IconKey,
} from '@douyinfe/semi-icons';
import { useTranslation } from 'react-i18next';
import { StatusContext } from '../../../../context/Status';
import { TokenService } from '../../../../services/token';
import {
  buildModelQuotaCandidateKey,
  buildModelQuotaCandidateLabel,
  buildModelQuotaCandidateMap,
  buildQuotaDimensionCapability,
  buildRateLimitRulesFromModelLimits,
  buildSharedPoolMemberLabel,
  createEmptyRateLimitRule,
  findAutoSelectedQuotaCandidate,
  findAutoSelectedSharedPoolMember,
  findSelectedQuotaCandidate,
  findSelectedQuotaMember,
  getExistingAllocationCredit,
  hasEnabledRateLimitDimension,
  normalizeRateLimitRules,
  parseQuotaRemainValue,
  sanitizeRuleEnabledState,
  sanitizeTokenModelConfig,
  serializeRateLimitRules,
} from '../../../../helpers/tokenModelRateLimits';

const { Text, Title } = Typography;

// 手动清空标记按“分组 + 模型”隔离，避免不同分组同名模型互相影响。
const buildManualQuotaSelectionKey = (groupValue, modelName) =>
  `${groupValue || ''}\x00${modelName || ''}`;

// 共享池子项还需要把一级配额池 id 纳入 key，避免切换共享池后误沿用旧清空状态。
const buildManualSharedPoolMemberKey = (groupValue, modelName, quotaId) =>
  `${groupValue || ''}\x00${modelName || ''}\x00${quotaId || ''}`;

// 空分组与 auto 分组都不支持模型级限流配置，但运行时分组语义仍由后端决定。
const isTokenModelRateLimitUnsupportedGroup = (groupValue) => {
  const normalizedGroup = `${groupValue || ''}`.trim();
  return normalizedGroup === '' || normalizedGroup === 'auto';
};

// EditTokenModal 处理令牌基础信息、模型白名单和模型级限流配置的创建/编辑。
const EditTokenModal = (props) => {
  const { t } = useTranslation();
  const [statusState] = useContext(StatusContext);
  const [loading, setLoading] = useState(false);
  const isMobile = useIsMobile();
  const formApiRef = useRef(null);
  const [models, setModels] = useState([]);
  const [groups, setGroups] = useState([]);
  const [rateLimitRules, setRateLimitRules] = useState([]);
  const [initialRateLimitRules, setInitialRateLimitRules] = useState([]);
  const [removedModelNames, setRemovedModelNames] = useState([]);
  const [selectedGroupValue, setSelectedGroupValue] = useState('');
  const [modelQuotaCandidateMap, setModelQuotaCandidateMap] = useState({});
  // 记录用户主动清空的一级选择，避免候选自动回填 effect 立刻把清空结果补回去。
  const manuallyClearedQuotaKeysRef = useRef(new Set());
  // 记录用户主动清空的共享池子项选择，允许用户先清空再重新选择。
  const manuallyClearedSharedPoolMemberKeysRef = useRef(new Set());
  const isEdit = props.editingToken.id !== undefined;
  // 候选只依赖当前规则涉及的模型名集合，避免用户改限流数值时重复请求同一批候选。
  const rateLimitRuleModelNamesKey = useMemo(
    () =>
      Array.from(
        new Set(
          rateLimitRules
            .map((rule) => `${rule?.model_name || ''}`.trim())
            .filter(Boolean),
        ),
      )
        .sort()
        .join('\x00'),
    [rateLimitRules],
  );

  const getInitValues = () => ({
    name: '',
    remain_quota: 0,
    expired_time: -1,
    unlimited_quota: true,
    token_model_limit_enabled: false,
    token_model_limit: [],
    allow_ips: '',
    group: '',
    cross_group_retry: false,
    token_model_rate_limits: [],
    tokenCount: 1,
  });

  // 统一同步本地规则状态与表单值，保证 reset/submit 行为一致。
  const syncRateLimitRules = (nextRules) => {
    const normalizedRules = normalizeRateLimitRules(nextRules);
    setRateLimitRules(normalizedRules);
    formApiRef.current?.setValue(
      'token_model_rate_limits',
      serializeRateLimitRules(normalizedRules),
    );
  };

  // 规范本地模型配置，但保留当前不可选模型的历史白名单与限流规则。
  const cleanupInvalidModels = (modelLimits, nextRules) => {
    const cleaned = sanitizeTokenModelConfig({
      modelLimits,
      rateLimitRules: nextRules,
    });
    setRemovedModelNames(cleaned.removedModelNames);
    return cleaned;
  };

  // handleModelLimitsChange 让规则块与“模型限制列表”保持单向同步，避免再手工增删规则。
  const handleModelLimitsChange = (nextModelLimits = []) => {
    const normalizedModelLimits = Array.isArray(nextModelLimits)
      ? nextModelLimits
      : [];
    formApiRef.current?.setValue('token_model_limit', normalizedModelLimits);
    syncRateLimitRules(
      buildRateLimitRulesFromModelLimits(normalizedModelLimits, rateLimitRules),
    );
  };

  // 切换为空分组或 auto 分组时立即清空模型级限流配置，避免隐藏区域继续提交旧规则。
  const handleGroupChange = (value) => {
    const nextGroupValue = value || '';
    setSelectedGroupValue(nextGroupValue);
    if (!isTokenModelRateLimitUnsupportedGroup(nextGroupValue)) {
      return;
    }
    manuallyClearedQuotaKeysRef.current.clear();
    manuallyClearedSharedPoolMemberKeysRef.current.clear();
    setModelQuotaCandidateMap({});
    syncRateLimitRules([]);
  };

  const handleCancel = () => {
    props.handleClose();
  };

  const setExpiredTime = (month, day, hour, minute) => {
    let now = new Date();
    let timestamp = now.getTime() / 1000;
    let seconds = month * 30 * 24 * 60 * 60;
    seconds += day * 24 * 60 * 60;
    seconds += hour * 60 * 60;
    seconds += minute * 60;
    if (!formApiRef.current) return;
    if (seconds !== 0) {
      timestamp += seconds;
      formApiRef.current.setValue('expired_time', timestamp2string(timestamp));
    } else {
      formApiRef.current.setValue('expired_time', -1);
    }
  };

  // 统一更新单条模型限流规则，避免 JSX 中出现重复的数组拷贝逻辑。
  const updateRateLimitRule = (index, patch) => {
    syncRateLimitRules(
      rateLimitRules.map((rule, ruleIndex) =>
        ruleIndex === index ? { ...rule, ...patch } : rule,
      ),
    );
  };

  // 保存前做最小前端校验，优先给出可读错误提示而不是依赖后端回包。
  const buildSubmitRateLimitRules = (
    groupValue,
    modelLimits = [],
    nextRules = rateLimitRules,
  ) => {
    // 仅把打开了“启用模型限流”开关的规则视为待提交规则；未打开的模型只作为白名单占位存在。
    const normalizedRules = normalizeRateLimitRules(nextRules);
    const enabledRules = normalizedRules.filter((rule) => rule.rule_enabled);
    // auto/空分组不接受模型级限流，提交时统一清空模型级限流配置。
    if (isTokenModelRateLimitUnsupportedGroup(groupValue)) {
      return [];
    }
    const seenModelNames = new Set();
    // 当用户配置了白名单时，限流规则也必须落在当前白名单内。
    const selectedModelSet = new Set(
      (Array.isArray(modelLimits) ? modelLimits : []).filter(Boolean),
    );

    for (const rule of enabledRules) {
      if (!rule.model_name) {
        showError(t('请选择模型限流规则对应的模型'));
        return null;
      }
      if (!hasEnabledRateLimitDimension(rule)) {
        showError(
          t(
            '模型 {{model}} 已开启模型限流，请至少启用并发、RPM、TPM 其中一项',
            {
              model: rule.model_name,
            },
          ),
        );
        return null;
      }
      if (seenModelNames.has(rule.model_name)) {
        showError(t('同一个模型只能配置一条限流规则'));
        return null;
      }
      seenModelNames.add(rule.model_name);
      const candidateCacheKey = buildModelQuotaCandidateKey(
        groupValue,
        rule.model_name,
      );
      const candidates = modelQuotaCandidateMap[candidateCacheKey] || [];
      const selectedCandidate = findSelectedQuotaCandidate(
        candidates,
        rule.quota_id,
      );
      const selectedMember = findSelectedQuotaMember(
        selectedCandidate,
        rule.model_quota_id,
      );
      if (!rule.quota_id) {
        showError(
          t('模型 {{model}} 请先选择关联配额池', {
            model: rule.model_name,
          }),
        );
        return null;
      }
      if (!selectedCandidate) {
        showError(
          t('模型 {{model}} 选择的关联配额池无效，请重新选择', {
            model: rule.model_name,
          }),
        );
        return null;
      }
      if (
        selectedCandidate.quota_type === 'shared_pool' &&
        !rule.model_quota_id
      ) {
        showError(
          t('模型 {{model}} 选择共享配额池后，必须继续选择共享池子项模型', {
            model: rule.model_name,
          }),
        );
        return null;
      }
      if (selectedCandidate.quota_type === 'shared_pool' && !selectedMember) {
        showError(
          t('模型 {{model}} 当前共享池子项模型无效，请重新选择', {
            model: rule.model_name,
          }),
        );
        return null;
      }
      const capability = buildQuotaDimensionCapability(selectedCandidate);
      if (
        rule.concurrency_limit_enabled &&
        !capability.concurrency_configured
      ) {
        showError(
          t('模型 {{model}} 关联的配额项未配置并发上限，不能启用并发限流', {
            model: rule.model_name,
          }),
        );
        return null;
      }
      if (rule.rpm_limit_enabled && !capability.rpm_configured) {
        showError(
          t('模型 {{model}} 关联的配额项未配置 RPM，不能启用 RPM 限流', {
            model: rule.model_name,
          }),
        );
        return null;
      }
      if (rule.tpm_limit_enabled && !capability.tpm_configured) {
        showError(
          t('模型 {{model}} 关联的配额项未配置 TPM，不能启用 TPM 限流', {
            model: rule.model_name,
          }),
        );
        return null;
      }
      if (selectedModelSet.size > 0 && !selectedModelSet.has(rule.model_name)) {
        showError(
          t('模型 {{model}} 不在当前可用模型列表中，请先调整模型限制列表', {
            model: rule.model_name,
          }),
        );
        return null;
      }
      // 提交前即时校验限流值是否超过当前配额池剩余额度，避免无效请求进入后端。
      if (rule.concurrency_limit_enabled) {
        const remainConcurrency = parseQuotaRemainValue(
          selectedCandidate.remain_concurrency,
        );
        const availableConcurrency =
          remainConcurrency === null
            ? null
            : remainConcurrency +
              getExistingAllocationCredit(
                initialRateLimitRules,
                rule,
                selectedCandidate,
                'concurrency_limit',
                'concurrency_limit_enabled',
              );
        if (
          availableConcurrency !== null &&
          rule.concurrency_limit > availableConcurrency
        ) {
          showError(
            t(
              '模型 {{model}} 的并发限制不能超过所选配额池剩余并发数 {{remain}}',
              {
                model: rule.model_name,
                remain: availableConcurrency,
              },
            ),
          );
          return null;
        }
      }
      // RPM 仅在当前配额池存在可比较剩余值时做前端阻断，保持与后端能力配置一致。
      if (rule.rpm_limit_enabled) {
        const remainRPM = parseQuotaRemainValue(selectedCandidate.remain_rpm);
        const availableRPM =
          remainRPM === null
            ? null
            : remainRPM +
              getExistingAllocationCredit(
                initialRateLimitRules,
                rule,
                selectedCandidate,
                'rpm_limit',
                'rpm_limit_enabled',
              );
        if (availableRPM !== null && rule.rpm_limit > availableRPM) {
          showError(
            t(
              '模型 {{model}} 的 RPM 限制不能超过所选配额池剩余 RPM {{remain}}',
              {
                model: rule.model_name,
                remain: availableRPM,
              },
            ),
          );
          return null;
        }
      }
      // TPM 仅在当前配额池存在可比较剩余值时做前端阻断，避免提交超额配置。
      if (rule.tpm_limit_enabled) {
        const remainTPM = parseQuotaRemainValue(selectedCandidate.remain_tpm);
        const availableTPM =
          remainTPM === null
            ? null
            : remainTPM +
              getExistingAllocationCredit(
                initialRateLimitRules,
                rule,
                selectedCandidate,
                'tpm_limit',
                'tpm_limit_enabled',
              );
        if (availableTPM !== null && rule.tpm_limit > availableTPM) {
          showError(
            t(
              '模型 {{model}} 的 TPM 限制不能超过所选配额池剩余 TPM {{remain}}',
              {
                model: rule.model_name,
                remain: availableTPM,
              },
            ),
          );
          return null;
        }
      }
    }

    return serializeRateLimitRules(enabledRules);
  };

  const loadModels = async () => {
    const { success, message, data } = await TokenService.getUserModels();
    if (success) {
      const categories = getModelCategories(t);
      let localModelOptions = data.map((model) => {
        let icon = null;
        for (const [key, category] of Object.entries(categories)) {
          if (key !== 'all' && category.filter({ model_name: model })) {
            icon = category.icon;
            break;
          }
        }
        return {
          label: (
            <span className='flex items-center gap-1'>
              {icon}
              {model}
            </span>
          ),
          value: model,
        };
      });
      setModels(localModelOptions);
    } else {
      showError(t(message));
    }
  };

  const loadGroups = async () => {
    const { success, message, data } = await TokenService.getUserGroups();
    if (success) {
      let localGroupOptions = Object.entries(data).map(([group, info]) => ({
        label: info.desc,
        value: group,
        ratio: info.ratio,
      }));
      if (statusState?.status?.default_use_auto_group) {
        if (localGroupOptions.some((group) => group.value === 'auto')) {
          localGroupOptions.sort((a, b) => (a.value === 'auto' ? -1 : 1));
        }
      }
      setGroups(localGroupOptions);
      // if (statusState?.status?.default_use_auto_group && formApiRef.current) {
      //   formApiRef.current.setValue('group', 'auto');
      // }
    } else {
      showError(t(message));
    }
  };

  const loadToken = async () => {
    setLoading(true);
    const { success, message, data } = await TokenService.getToken(
      props.editingToken.id,
    );
    if (success) {
      if (data.expired_time !== -1) {
        data.expired_time = timestamp2string(data.expired_time);
      }
      if (data.token_model_limit !== '') {
        data.token_model_limit = data.token_model_limit.split(',');
      } else {
        data.token_model_limit = [];
      }
      const nextRateLimitRules = normalizeRateLimitRules(
        data.token_model_rate_limits,
      );
      setInitialRateLimitRules(nextRateLimitRules);
      setSelectedGroupValue(data.group || '');
      // 已有白名单时，规则块按白名单顺序回填；无白名单时保留旧规则，兼容历史数据编辑。
      syncRateLimitRules(
        Array.isArray(data.token_model_limit) && data.token_model_limit.length > 0
          ? buildRateLimitRulesFromModelLimits(
              data.token_model_limit,
              nextRateLimitRules,
            )
          : nextRateLimitRules,
      );
      if (formApiRef.current) {
        formApiRef.current.setValues({ ...getInitValues(), ...data });
      }
    } else {
      showError(message);
    }
    setLoading(false);
  };

  useEffect(() => {
    if (formApiRef.current) {
      if (!isEdit) {
        formApiRef.current.setValues(getInitValues());
        syncRateLimitRules([]);
        setInitialRateLimitRules([]);
        setSelectedGroupValue('');
      }
    }
    loadModels();
    loadGroups();
  }, [props.editingToken.id]);

  useEffect(() => {
    if (props.visiable) {
      if (isEdit) {
        loadToken();
      } else {
        formApiRef.current?.setValues(getInitValues());
        syncRateLimitRules([]);
        setInitialRateLimitRules([]);
        setRemovedModelNames([]);
        setSelectedGroupValue('');
      }
    } else {
      formApiRef.current?.reset();
      syncRateLimitRules([]);
      setInitialRateLimitRules([]);
      setRemovedModelNames([]);
      setSelectedGroupValue('');
      setModelQuotaCandidateMap({});
    }
    // 每次打开/关闭弹窗都重置手动清空标记，避免上一次编辑影响下一次编辑。
    manuallyClearedQuotaKeysRef.current.clear();
    manuallyClearedSharedPoolMemberKeysRef.current.clear();
  }, [props.visiable, props.editingToken.id]);

  useEffect(() => {
    if (!props.visiable || models.length === 0 || !formApiRef.current) {
      return;
    }

    const currentModelLimits =
      formApiRef.current.getValue('token_model_limit') || [];
    const cleaned = cleanupInvalidModels(currentModelLimits, rateLimitRules);
    const nextRulesForRender =
      Array.isArray(cleaned.sanitizedModelLimits) &&
      cleaned.sanitizedModelLimits.length > 0
        ? buildRateLimitRulesFromModelLimits(
            cleaned.sanitizedModelLimits,
            cleaned.sanitizedRateLimitRules,
          )
        : cleaned.sanitizedRateLimitRules;

    if (
      cleaned.sanitizedModelLimits.join(',') !== currentModelLimits.join(',')
    ) {
      formApiRef.current.setValue('token_model_limit', cleaned.sanitizedModelLimits);
    }
    if (JSON.stringify(nextRulesForRender) !== JSON.stringify(rateLimitRules)) {
      syncRateLimitRules(nextRulesForRender);
    }
  }, [models, props.visiable, rateLimitRules, props.editingToken.id]);

  // 当前分组或规则模型变化时拉取关联配额池候选，供一级/二级选择框联动使用。
  useEffect(() => {
    if (
      !props.visiable ||
      isTokenModelRateLimitUnsupportedGroup(selectedGroupValue)
    ) {
      if (isTokenModelRateLimitUnsupportedGroup(selectedGroupValue)) {
        setModelQuotaCandidateMap({});
      }
      return;
    }
    const uniqueModelNames = rateLimitRuleModelNamesKey
      ? rateLimitRuleModelNamesKey.split('\x00').filter(Boolean)
      : [];
    if (uniqueModelNames.length === 0) {
      setModelQuotaCandidateMap({});
      return;
    }
    let cancelled = false;
    const loadModelQuotaCandidates = async () => {
      const { success, message, data } =
        await TokenService.getModelQuotaCandidates(
          uniqueModelNames[0],
          selectedGroupValue,
        );
      if (!success) {
        showError(t(message || '获取关联配额池候选失败'));
        return;
      }
      const nextCandidateMap = buildModelQuotaCandidateMap(
        data?.candidates,
        selectedGroupValue,
        uniqueModelNames,
      );
      if (!cancelled) {
        setModelQuotaCandidateMap(nextCandidateMap);
      }
    };
    loadModelQuotaCandidates();
    return () => {
      cancelled = true;
    };
  }, [props.visiable, rateLimitRuleModelNamesKey, selectedGroupValue, t]);

  // 候选加载完成后自动补全唯一可确定的一级/二级选择，并清理失效选择。
  useEffect(() => {
    if (
      !props.visiable ||
      isTokenModelRateLimitUnsupportedGroup(selectedGroupValue) ||
      rateLimitRules.length === 0
    ) {
      return;
    }
    const nextRules = rateLimitRules.map((rule) => {
      const cacheKey = buildModelQuotaCandidateKey(
        selectedGroupValue,
        rule.model_name,
      );
      // 候选仍在异步加载时保留当前规则，避免先把已回显的开关和配额池清空。
      if (
        rule.model_name &&
        !Object.prototype.hasOwnProperty.call(modelQuotaCandidateMap, cacheKey)
      ) {
        return rule;
      }
      const candidates = modelQuotaCandidateMap[cacheKey] || [];
      if (!rule.model_name) {
        return rule;
      }
      const selectedCandidate = findSelectedQuotaCandidate(
        candidates,
        rule.quota_id,
      );
      const manualQuotaSelectionKey = buildManualQuotaSelectionKey(
        selectedGroupValue,
        rule.model_name,
      );
      if (selectedCandidate) {
        if (selectedCandidate.quota_type !== 'shared_pool') {
          return {
            ...rule,
            model_quota_id: undefined,
            ...sanitizeRuleEnabledState(
              rule,
              buildQuotaDimensionCapability(selectedCandidate),
            ),
          };
        }
        const selectedMember = findSelectedQuotaMember(
          selectedCandidate,
          rule.model_quota_id,
        );
        const manualSharedPoolMemberKey = buildManualSharedPoolMemberKey(
          selectedGroupValue,
          rule.model_name,
          selectedCandidate.quota_id,
        );
        const autoSelectedMember =
          selectedMember ||
          (manuallyClearedSharedPoolMemberKeysRef.current.has(
            manualSharedPoolMemberKey,
          )
            ? null
            : findAutoSelectedSharedPoolMember(
                selectedCandidate,
                selectedGroupValue,
                rule.model_name,
              ));
        return {
          ...rule,
          model_quota_id: autoSelectedMember?.model_quota_id,
          ...sanitizeRuleEnabledState(
            rule,
            buildQuotaDimensionCapability(selectedCandidate),
          ),
        };
      }
      if (manuallyClearedQuotaKeysRef.current.has(manualQuotaSelectionKey)) {
        return {
          ...rule,
          quota_id: undefined,
          model_quota_id: undefined,
          ...sanitizeRuleEnabledState(
            rule,
            buildQuotaDimensionCapability(null),
          ),
        };
      }
      const autoSelectedCandidate = findAutoSelectedQuotaCandidate(
        candidates,
        selectedGroupValue,
        rule.model_name,
      );
      if (!autoSelectedCandidate) {
        return {
          ...rule,
          quota_id: undefined,
          model_quota_id: undefined,
          ...sanitizeRuleEnabledState(
            rule,
            buildQuotaDimensionCapability(null),
          ),
        };
      }
      const autoSelectedMember =
        autoSelectedCandidate.quota_type === 'shared_pool'
          ? manuallyClearedSharedPoolMemberKeysRef.current.has(
              buildManualSharedPoolMemberKey(
                selectedGroupValue,
                rule.model_name,
                autoSelectedCandidate.quota_id,
              ),
            )
            ? null
            : findAutoSelectedSharedPoolMember(
                autoSelectedCandidate,
                selectedGroupValue,
                rule.model_name,
              )
          : null;
      return {
        ...rule,
        quota_id: autoSelectedCandidate.quota_id,
        model_quota_id: autoSelectedMember?.model_quota_id,
        ...sanitizeRuleEnabledState(
          rule,
          buildQuotaDimensionCapability(autoSelectedCandidate),
        ),
      };
    });
    if (JSON.stringify(nextRules) !== JSON.stringify(rateLimitRules)) {
      syncRateLimitRules(nextRules);
    }
  }, [
    modelQuotaCandidateMap,
    props.visiable,
    rateLimitRules,
    selectedGroupValue,
  ]);

  const generateRandomSuffix = () => {
    const characters =
      'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
    let result = '';
    for (let i = 0; i < 6; i++) {
      result += characters.charAt(
        Math.floor(Math.random() * characters.length),
      );
    }
    return result;
  };

  // 一级候选确认后同步更新 quota_id / model_quota_id，并裁剪不再合法的维度开关。
  const applyQuotaCandidateChange = (index, currentRule, nextCandidate) => {
    const autoSelectedMember =
      nextCandidate.quota_type === 'shared_pool'
        ? findAutoSelectedSharedPoolMember(
            nextCandidate,
            selectedGroupValue,
            currentRule?.model_name,
          )
        : null;
    updateRateLimitRule(index, {
      quota_id: nextCandidate.quota_id,
      model_quota_id: autoSelectedMember?.model_quota_id,
      ...sanitizeRuleEnabledState(
        currentRule,
        buildQuotaDimensionCapability(nextCandidate),
      ),
    });
  };

  // 一级候选切换时，普通模型项若与当前规则的模型名或分组不一致，需要先让用户确认。
  const handleQuotaCandidateChange = (index, quotaId) => {
    const currentRule = rateLimitRules[index];
    const manualQuotaSelectionKey = buildManualQuotaSelectionKey(
      selectedGroupValue,
      currentRule?.model_name,
    );
    const cacheKey = buildModelQuotaCandidateKey(
      selectedGroupValue,
      currentRule?.model_name,
    );
    const candidates = modelQuotaCandidateMap[cacheKey] || [];
    const nextCandidate = findSelectedQuotaCandidate(candidates, quotaId);
    if (!nextCandidate) {
      manuallyClearedQuotaKeysRef.current.add(manualQuotaSelectionKey);
      updateRateLimitRule(index, {
        quota_id: undefined,
        model_quota_id: undefined,
        ...sanitizeRuleEnabledState(
          currentRule,
          buildQuotaDimensionCapability(null),
        ),
      });
      return;
    }
    manuallyClearedQuotaKeysRef.current.delete(manualQuotaSelectionKey);
    manuallyClearedSharedPoolMemberKeysRef.current.delete(
      buildManualSharedPoolMemberKey(
        selectedGroupValue,
        currentRule?.model_name,
        nextCandidate.quota_id,
      ),
    );
    const isNormalCandidateMismatched =
      nextCandidate.quota_type !== 'shared_pool' &&
      (nextCandidate.model_name !== currentRule?.model_name ||
        `${nextCandidate.group || ''}`.trim() !==
          `${selectedGroupValue || ''}`.trim());
    if (isNormalCandidateMismatched) {
      Modal.confirm({
        title: t('确认配额池选择'),
        content: t(
          '当前所选配额池与当前模型名或分组不一致，确认后将继续保留本次选择',
        ),
        okText: t('确认'),
        cancelText: t('取消'),
        onOk: () => {
          applyQuotaCandidateChange(index, currentRule, nextCandidate);
        },
      });
      return;
    }
    applyQuotaCandidateChange(index, currentRule, nextCandidate);
  };

  // 二级共享池子项切换时，若与当前规则的模型名或分组不一致则立即要求用户确认。
  const handleSharedPoolMemberChange = (
    index,
    modelQuotaId,
    selectedCandidate,
  ) => {
    const currentRule = rateLimitRules[index];
    const nextMember = findSelectedQuotaMember(selectedCandidate, modelQuotaId);
    const manualSharedPoolMemberKey = buildManualSharedPoolMemberKey(
      selectedGroupValue,
      currentRule?.model_name,
      selectedCandidate?.quota_id,
    );
    if (!nextMember) {
      manuallyClearedSharedPoolMemberKeysRef.current.add(
        manualSharedPoolMemberKey,
      );
      updateRateLimitRule(index, { model_quota_id: undefined });
      return;
    }
    manuallyClearedSharedPoolMemberKeysRef.current.delete(
      manualSharedPoolMemberKey,
    );
    const isSharedPoolMemberMismatched =
      nextMember.model_name !== currentRule?.model_name ||
      `${nextMember.group || ''}`.trim() !==
        `${selectedGroupValue || ''}`.trim();
    if (isSharedPoolMemberMismatched) {
      Modal.confirm({
        title: t('确认共享池子项选择'),
        content: t(
          '当前所选共享池子项与当前模型名或分组不一致，确认后将继续保留本次选择',
        ),
        okText: t('确认'),
        cancelText: t('取消'),
        onOk: () => {
          updateRateLimitRule(index, {
            model_quota_id: nextMember.model_quota_id,
          });
        },
      });
      return;
    }
    updateRateLimitRule(index, { model_quota_id: nextMember.model_quota_id });
  };

  const submit = async (values) => {
    setLoading(true);
    const cleaned = cleanupInvalidModels(values.token_model_limit, rateLimitRules);
    const normalizedRateLimitRules = buildSubmitRateLimitRules(
      values.group,
      cleaned.sanitizedModelLimits,
      cleaned.sanitizedRateLimitRules,
    );
    if (normalizedRateLimitRules === null) {
      setLoading(false);
      return;
    }
    const submitRateLimitRules = normalizedRateLimitRules;
    if (isEdit) {
      let { tokenCount: _tc, ...localInputs } = values;
      localInputs.remain_quota = parseInt(localInputs.remain_quota);
      if (localInputs.expired_time !== -1) {
        let time = Date.parse(localInputs.expired_time);
        if (isNaN(time)) {
          showError(t('过期时间格式错误！'));
          setLoading(false);
          return;
        }
        localInputs.expired_time = Math.ceil(time / 1000);
      }
      localInputs.token_model_limit = cleaned.sanitizedModelLimits.join(',');
      localInputs.token_model_limit_enabled =
        localInputs.token_model_limit.length > 0;
      localInputs.token_model_rate_limits = submitRateLimitRules;
      const { success, message } = await TokenService.updateToken({
        ...localInputs,
        id: parseInt(props.editingToken.id),
      });
      if (success) {
        // 令牌模型限流保存成功后，通知模型配额页刷新剩余额度与“令牌名 - 限流配置”展示。
        emitTokenModelQuotaRefresh({ source: 'token-edit-update' });
        props.refresh();
        props.handleClose({ status: 'success', message: t('令牌更新成功！') });
      } else {
        props.handleClose({ status: 'error', message: t(message || '令牌更新失败') });
      }
    } else {
      const count = parseInt(values.tokenCount, 10) || 1;
      let successCount = 0;
      for (let i = 0; i < count; i++) {
        let { tokenCount: _tc, ...localInputs } = values;
        const baseName =
          values.name.trim() === '' ? 'default' : values.name.trim();
        if (i !== 0 || values.name.trim() === '') {
          localInputs.name = `${baseName}-${generateRandomSuffix()}`;
        } else {
          localInputs.name = baseName;
        }
        localInputs.remain_quota = parseInt(localInputs.remain_quota);

        if (localInputs.expired_time !== -1) {
          let time = Date.parse(localInputs.expired_time);
          if (isNaN(time)) {
            showError(t('过期时间格式错误！'));
            setLoading(false);
            break;
          }
          localInputs.expired_time = Math.ceil(time / 1000);
        }
        localInputs.token_model_limit = cleaned.sanitizedModelLimits.join(',');
        localInputs.token_model_limit_enabled =
          localInputs.token_model_limit.length > 0;
        localInputs.token_model_rate_limits = submitRateLimitRules;
        const { success, message } =
          await TokenService.createToken(localInputs);
        if (success) {
          successCount++;
        } else {
          showError(t(message));
          break;
        }
      }
      if (successCount > 0) {
        showSuccess(t('令牌创建成功，请在列表页面点击复制获取令牌！'));
        // 新建令牌成功后可能新增限流分配，通知模型配额页同步刷新。
        emitTokenModelQuotaRefresh({ source: 'token-edit-create' });
        props.refresh();
        props.handleClose();
      }
    }
    setLoading(false);
    formApiRef.current?.setValues(getInitValues());
    syncRateLimitRules([]);
    setInitialRateLimitRules([]);
  };

  return (
    <SideSheet
      placement={isEdit ? 'right' : 'left'}
      title={
        <Space>
          {isEdit ? (
            <Tag color='blue' shape='circle'>
              {t('更新')}
            </Tag>
          ) : (
            <Tag color='green' shape='circle'>
              {t('新建')}
            </Tag>
          )}
          <Title heading={4} className='m-0'>
            {isEdit ? t('更新令牌信息') : t('创建新的令牌')}
          </Title>
        </Space>
      }
      bodyStyle={{ padding: '0' }}
      visible={props.visiable}
      width={isMobile ? '100%' : 600}
      footer={
        <div className='flex justify-end bg-white'>
          <Space>
            <Button
              theme='solid'
              className='!rounded-lg'
              onClick={() => formApiRef.current?.submitForm()}
              icon={<IconSave />}
              loading={loading}
            >
              {t('提交')}
            </Button>
            <Button
              theme='light'
              className='!rounded-lg'
              type='primary'
              onClick={handleCancel}
              icon={<IconClose />}
            >
              {t('取消')}
            </Button>
          </Space>
        </div>
      }
      closeIcon={null}
      onCancel={() => handleCancel()}
    >
      <Spin spinning={loading}>
        <Form
          key={isEdit ? 'edit' : 'new'}
          initValues={getInitValues()}
          getFormApi={(api) => (formApiRef.current = api)}
          onSubmit={submit}
        >
          {({ values }) => (
            <div className='p-2'>
              {/* 基本信息 */}
              <Card className='!rounded-2xl shadow-sm border-0'>
                <div className='flex items-center mb-2'>
                  <Avatar size='small' color='blue' className='mr-2 shadow-md'>
                    <IconKey size={16} />
                  </Avatar>
                  <div>
                    <Text className='text-lg font-medium'>{t('基本信息')}</Text>
                    <div className='text-xs text-gray-600'>
                      {t('设置令牌的基本信息')}
                    </div>
                  </div>
                </div>
                <Row gutter={12}>
                  <Col span={24}>
                    <Form.Input
                      field='name'
                      label={t('名称')}
                      placeholder={t('请输入名称')}
                      rules={[{ required: true, message: t('请输入名称') }]}
                      showClear
                    />
                  </Col>
                  <Col span={24}>
                    {groups.length > 0 ? (
                      <Form.Select
                        field='group'
                        label={t('令牌分组')}
                        placeholder={t('令牌分组，默认为用户的分组')}
                        optionList={groups}
                        renderOptionItem={renderGroupOption}
                        showClear
                        onChange={(value) => handleGroupChange(value)}
                        style={{ width: '100%' }}
                      />
                    ) : (
                      <Form.Select
                        placeholder={t('管理员未设置用户可选分组')}
                        disabled
                        label={t('令牌分组')}
                        style={{ width: '100%' }}
                      />
                    )}
                  </Col>
                  <Col
                    span={24}
                    style={{
                      display: values.group === 'auto' ? 'block' : 'none',
                    }}
                  >
                    <Form.Switch
                      field='cross_group_retry'
                      label={t('跨分组重试')}
                      size='default'
                      extraText={t(
                        '开启后，当前分组渠道失败时会按顺序尝试下一个分组的渠道',
                      )}
                    />
                  </Col>
                  <Col xs={24} sm={24} md={24} lg={10} xl={10}>
                    <Form.DatePicker
                      field='expired_time'
                      label={t('过期时间')}
                      type='dateTime'
                      placeholder={t('请选择过期时间')}
                      rules={[
                        { required: true, message: t('请选择过期时间') },
                        {
                          validator: (rule, value) => {
                            // 允许 -1 表示永不过期，也允许空值在必填校验时被拦截
                            if (value === -1 || !value)
                              return Promise.resolve();
                            const time = Date.parse(value);
                            if (isNaN(time)) {
                              return Promise.reject(t('过期时间格式错误！'));
                            }
                            if (time <= Date.now()) {
                              return Promise.reject(
                                t('过期时间不能早于当前时间！'),
                              );
                            }
                            return Promise.resolve();
                          },
                        },
                      ]}
                      showClear
                      style={{ width: '100%' }}
                    />
                  </Col>
                  <Col xs={24} sm={24} md={24} lg={14} xl={14}>
                    <Form.Slot label={t('过期时间快捷设置')}>
                      <Space wrap>
                        <Button
                          theme='light'
                          type='primary'
                          onClick={() => setExpiredTime(0, 0, 0, 0)}
                        >
                          {t('永不过期')}
                        </Button>
                        <Button
                          theme='light'
                          type='tertiary'
                          onClick={() => setExpiredTime(1, 0, 0, 0)}
                        >
                          {t('一个月')}
                        </Button>
                        <Button
                          theme='light'
                          type='tertiary'
                          onClick={() => setExpiredTime(0, 1, 0, 0)}
                        >
                          {t('一天')}
                        </Button>
                        <Button
                          theme='light'
                          type='tertiary'
                          onClick={() => setExpiredTime(0, 0, 1, 0)}
                        >
                          {t('一小时')}
                        </Button>
                      </Space>
                    </Form.Slot>
                  </Col>
                  {!isEdit && (
                    <Col span={24}>
                      <Form.InputNumber
                        field='tokenCount'
                        label={t('新建数量')}
                        min={1}
                        extraText={t('批量创建时会在名称后自动添加随机后缀')}
                        rules={[
                          { required: true, message: t('请输入新建数量') },
                        ]}
                        style={{ width: '100%' }}
                      />
                    </Col>
                  )}
                </Row>
              </Card>

              {/* 额度设置 */}
              <Card className='!rounded-2xl shadow-sm border-0'>
                <div className='flex items-center mb-2'>
                  <Avatar size='small' color='green' className='mr-2 shadow-md'>
                    <IconCreditCard size={16} />
                  </Avatar>
                  <div>
                    <Text className='text-lg font-medium'>{t('额度设置')}</Text>
                    <div className='text-xs text-gray-600'>
                      {t('设置令牌可用额度和数量')}
                    </div>
                  </div>
                </div>
                <Row gutter={12}>
                  <Col span={24}>
                    <Form.AutoComplete
                      field='remain_quota'
                      label={t('额度')}
                      placeholder={t('请输入额度')}
                      type='number'
                      disabled={values.unlimited_quota}
                      extraText={renderQuotaWithPrompt(values.remain_quota)}
                      rules={
                        values.unlimited_quota
                          ? []
                          : [{ required: true, message: t('请输入额度') }]
                      }
                      data={[
                        { value: 500000, label: '1$' },
                        { value: 5000000, label: '10$' },
                        { value: 25000000, label: '50$' },
                        { value: 50000000, label: '100$' },
                        { value: 250000000, label: '500$' },
                        { value: 500000000, label: '1000$' },
                      ]}
                    />
                  </Col>
                  <Col span={24}>
                    <Form.Switch
                      field='unlimited_quota'
                      label={t('无限额度')}
                      size='default'
                      extraText={t(
                        '令牌的额度仅用于限制令牌本身的最大额度使用量，实际的使用受到账户的剩余额度限制',
                      )}
                    />
                  </Col>
                </Row>
              </Card>

              {/* 访问限制 */}
              <Card className='!rounded-2xl shadow-sm border-0'>
                <div className='flex items-center mb-2'>
                  <Avatar
                    size='small'
                    color='purple'
                    className='mr-2 shadow-md'
                  >
                    <IconLink size={16} />
                  </Avatar>
                  <div>
                    <Text className='text-lg font-medium'>{t('访问限制')}</Text>
                    <div className='text-xs text-gray-600'>
                      {t('设置令牌的访问限制')}
                    </div>
                  </div>
                </div>
                <Row gutter={12}>
                  <Col span={24}>
                    <Form.Select
                      field='token_model_limit'
                      label={t('模型限制列表')}
                      placeholder={t(
                        '请选择该令牌支持的模型，留空支持所有模型',
                      )}
                      multiple
                      optionList={models}
                      extraText={t('非必要，不建议启用模型限制')}
                      filter={selectFilter}
                      autoClearSearchValue={false}
                      searchPosition='dropdown'
                      showClear
                      onChange={(value) => handleModelLimitsChange(value)}
                      style={{ width: '100%' }}
                    />
                  </Col>
                  <Col span={24}>
                    <Form.Slot label={t('模型限流配置')}>
                      <div className='w-full'>
                        <div className='flex items-center justify-between mb-3'>
                          <div className='text-xs text-gray-600'>
                            {isTokenModelRateLimitUnsupportedGroup(
                              values.group,
                            )
                              ? t(
                                  '未选择分组或 auto 分组不支持模型级限流配置；切换后会自动清空已有模型级限流配置',
                                )
                              : t(
                                  '规则块会随上方模型限制列表自动生成；移除模型时，对应规则也会一并移除',
                                )}
                          </div>
                        </div>
                        {!isTokenModelRateLimitUnsupportedGroup(
                          values.group,
                        ) ? (
                          <>
                            {removedModelNames.length > 0 ? (
                              <div className='mb-3 text-xs text-amber-600'>
                                {t(
                                  '检测到已删除模型，保存时会自动清理：{{models}}',
                                  {
                                    models: removedModelNames.join(', '),
                                  },
                                )}
                              </div>
                            ) : null}
                            {rateLimitRules.length === 0 ? (
                              <Tag color='white' shape='circle'>
                                {Array.isArray(values.token_model_limit) &&
                                values.token_model_limit.length > 0
                                  ? t(
                                      '已选模型尚未生成限流规则，请重新选择模型后重试',
                                    )
                                  : t(
                                      '请先在上方选择模型，随后按模型逐条配置限流',
                                    )}
                              </Tag>
                            ) : (
                              rateLimitRules.map((rule, index) => {
                                const candidateCacheKey =
                                  buildModelQuotaCandidateKey(
                                    selectedGroupValue,
                                    rule.model_name,
                                  );
                                const currentCandidates =
                                  modelQuotaCandidateMap[candidateCacheKey] ||
                                  [];
                                const currentCandidateOptions =
                                  currentCandidates.map((candidate) => ({
                                    label: buildModelQuotaCandidateLabel(
                                      candidate,
                                      t,
                                    ),
                                    value: candidate.quota_id,
                                  }));
                                const selectedQuotaCandidate =
                                  findSelectedQuotaCandidate(
                                    currentCandidates,
                                    rule.quota_id,
                                  );
                                const selectedQuotaCapability =
                                  buildQuotaDimensionCapability(
                                    selectedQuotaCandidate,
                                  );
                                const selectedQuotaMembers = Array.isArray(
                                  selectedQuotaCandidate?.members,
                                )
                                  ? selectedQuotaCandidate.members
                                  : [];
                                const selectedQuotaMemberOptions =
                                  selectedQuotaMembers.map((member) => ({
                                    label: buildSharedPoolMemberLabel(member),
                                    value: member.model_quota_id,
                                  }));
                                const selectedQuotaMember =
                                  findSelectedQuotaMember(
                                    selectedQuotaCandidate,
                                    rule.model_quota_id,
                                  );
                                const concurrencyConfigured =
                                  !!selectedQuotaCapability?.concurrency_configured;
                                const rpmConfigured =
                                  !!selectedQuotaCapability?.rpm_configured;
                                const tpmConfigured =
                                  !!selectedQuotaCapability?.tpm_configured;

                                return (
                                  <Card
                                    key={`${rule.model_name || 'rule'}-${index}`}
                                    className='!rounded-xl border border-gray-100 mb-3 shadow-none'
                                    bodyStyle={{ padding: 12 }}
                                  >
                                    <div className='flex items-center justify-between mb-3'>
                                      <Tag color='blue' shape='circle'>
                                        {rule.model_name || t('未选择模型')}
                                      </Tag>
                                      <div className='flex items-center gap-2'>
                                        <Text>{t('启用模型限流')}</Text>
                                        <SemiSwitch
                                          checked={rule.rule_enabled}
                                          disabled={
                                            isTokenModelRateLimitUnsupportedGroup(
                                              values.group,
                                            ) || !rule.model_name
                                          }
                                          onChange={(checked) =>
                                            updateRateLimitRule(index, {
                                              rule_enabled: checked,
                                            })
                                          }
                                        />
                                      </div>
                                    </div>
                                    <Row gutter={12}>
                                      {rule.rule_enabled ? (
                                        <>
                                          <Col span={24}>
                                            <Text className='block mb-1'>
                                              {t('关联配额池')}
                                            </Text>
                                            <SemiSelect
                                              value={rule.quota_id}
                                              optionList={
                                                currentCandidateOptions
                                              }
                                              showClear
                                              searchable
                                              disabled={
                                                isTokenModelRateLimitUnsupportedGroup(
                                                  values.group,
                                                ) ||
                                                !rule.model_name
                                              }
                                              onChange={(value) =>
                                                handleQuotaCandidateChange(
                                                  index,
                                                  value,
                                                )
                                              }
                                              style={{ width: '100%' }}
                                            />
                                            {rule.model_name &&
                                            currentCandidateOptions.length ===
                                              0 ? (
                                              <div className='mt-1 text-xs text-red-500'>
                                                {t(
                                                  '当前模型暂无可用的普通模型项或共享配额池候选，请先检查模型配额配置。',
                                                )}
                                              </div>
                                            ) : null}
                                            {selectedQuotaCandidate ? (
                                              <div className='mt-1 text-xs text-gray-500'>
                                                {t(
                                                  '当前配额池：并发{{concurrency}} / RPM{{rpm}} / TPM{{tpm}}',
                                                  {
                                                    concurrency:
                                                      selectedQuotaCandidate.concurrency ===
                                                        null ||
                                                      selectedQuotaCandidate.concurrency ===
                                                        undefined
                                                        ? t('未配置')
                                                        : selectedQuotaCandidate.concurrency,
                                                    rpm:
                                                      selectedQuotaCandidate.rpm ===
                                                        null ||
                                                      selectedQuotaCandidate.rpm ===
                                                        undefined
                                                        ? t('未配置')
                                                        : selectedQuotaCandidate.rpm,
                                                    tpm:
                                                      selectedQuotaCandidate.tpm ===
                                                        null ||
                                                      selectedQuotaCandidate.tpm ===
                                                        undefined
                                                        ? t('未配置')
                                                        : selectedQuotaCandidate.tpm,
                                                  },
                                                )}
                                              </div>
                                            ) : null}
                                          </Col>
                                          {selectedQuotaCandidate?.quota_type ===
                                          'shared_pool' ? (
                                            <Col span={24}>
                                              <Text className='block mb-1'>
                                                {t('共享池子项模型')}
                                              </Text>
                                              <SemiSelect
                                                value={rule.model_quota_id}
                                                optionList={
                                                  selectedQuotaMemberOptions
                                                }
                                                showClear
                                                searchable
                                                disabled={
                                                  isTokenModelRateLimitUnsupportedGroup(
                                                    values.group,
                                                  )
                                                }
                                                onChange={(value) =>
                                                  handleSharedPoolMemberChange(
                                                    index,
                                                    value,
                                                    selectedQuotaCandidate,
                                                  )
                                                }
                                                style={{ width: '100%' }}
                                              />
                                              <div className='mt-1 text-xs text-gray-500'>
                                                {selectedQuotaMember
                                                  ? t(
                                                      '当前展示归属：{{member}}',
                                                      {
                                                        member:
                                                          buildSharedPoolMemberLabel(
                                                            selectedQuotaMember,
                                                          ),
                                                      },
                                                    )
                                                  : t(
                                                      '请选择共享池子项模型；该值会作为展示归属与删除阻断判定目标。',
                                                    )}
                                              </div>
                                            </Col>
                                          ) : null}
                                          <Col span={24}>
                                            <div className='flex items-center justify-between mb-2'>
                                              <Text>{t('并发限制')}</Text>
                                              <SemiSwitch
                                                checked={
                                                  rule.concurrency_limit_enabled
                                                }
                                                disabled={
                                                  isTokenModelRateLimitUnsupportedGroup(
                                                    values.group,
                                                  ) || !concurrencyConfigured
                                                }
                                                onChange={(checked) =>
                                                  updateRateLimitRule(index, {
                                                    concurrency_limit_enabled:
                                                      checked,
                                                  })
                                                }
                                              />
                                            </div>
                                            <SemiInputNumber
                                              min={1}
                                              disabled={
                                                isTokenModelRateLimitUnsupportedGroup(
                                                  values.group,
                                                ) ||
                                                !rule.concurrency_limit_enabled ||
                                                !concurrencyConfigured
                                              }
                                              value={rule.concurrency_limit}
                                              onChange={(value) =>
                                                updateRateLimitRule(index, {
                                                  concurrency_limit: value || 1,
                                                })
                                              }
                                              style={{ width: '100%' }}
                                            />
                                          </Col>
                                          <Col span={24}>
                                            <div className='flex items-center justify-between mb-2'>
                                              <Text>{t('RPM 限制')}</Text>
                                              <SemiSwitch
                                                checked={rule.rpm_limit_enabled}
                                                disabled={
                                                  isTokenModelRateLimitUnsupportedGroup(
                                                    values.group,
                                                  ) || !rpmConfigured
                                                }
                                                onChange={(checked) =>
                                                  updateRateLimitRule(index, {
                                                    rpm_limit_enabled: checked,
                                                  })
                                                }
                                              />
                                            </div>
                                            <SemiInputNumber
                                              min={1}
                                              disabled={
                                                isTokenModelRateLimitUnsupportedGroup(
                                                  values.group,
                                                ) ||
                                                !rule.rpm_limit_enabled ||
                                                !rpmConfigured
                                              }
                                              value={rule.rpm_limit}
                                              onChange={(value) =>
                                                updateRateLimitRule(index, {
                                                  rpm_limit: value || 1,
                                                })
                                              }
                                              style={{ width: '100%' }}
                                            />
                                          </Col>
                                          <Col span={24}>
                                            <div className='flex items-center justify-between mb-2'>
                                              <Text>{t('TPM 限制')}</Text>
                                              <SemiSwitch
                                                checked={rule.tpm_limit_enabled}
                                                disabled={
                                                  isTokenModelRateLimitUnsupportedGroup(
                                                    values.group,
                                                  ) || !tpmConfigured
                                                }
                                                onChange={(checked) =>
                                                  updateRateLimitRule(index, {
                                                    tpm_limit_enabled: checked,
                                                  })
                                                }
                                              />
                                            </div>
                                            <SemiInputNumber
                                              min={1}
                                              disabled={
                                                isTokenModelRateLimitUnsupportedGroup(
                                                  values.group,
                                                ) ||
                                                !rule.tpm_limit_enabled ||
                                                !tpmConfigured
                                              }
                                              value={rule.tpm_limit}
                                              onChange={(value) =>
                                                updateRateLimitRule(index, {
                                                  tpm_limit: value || 1,
                                                })
                                              }
                                              style={{ width: '100%' }}
                                            />
                                          </Col>
                                        </>
                                      ) : null}
                                    </Row>
                                  </Card>
                                );
                              })
                            )}
                          </>
                        ) : null}
                      </div>
                    </Form.Slot>
                  </Col>
                  <Col span={24}>
                    <Form.TextArea
                      field='allow_ips'
                      label={t('IP白名单（支持CIDR表达式）')}
                      placeholder={t('允许的IP，一行一个，不填写则不限制')}
                      autosize
                      rows={1}
                      extraText={t(
                        '请勿过度信任此功能，IP可能被伪造，请配合nginx和cdn等网关使用',
                      )}
                      showClear
                      style={{ width: '100%' }}
                    />
                  </Col>
                </Row>
              </Card>
            </div>
          )}
        </Form>
      </Spin>
    </SideSheet>
  );
};

export default EditTokenModal;
