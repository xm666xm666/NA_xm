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

// 默认规则保持最小字段集，避免向后端提交无意义的冗余值。
export const createEmptyRateLimitRule = () => ({
  model_name: '',
  quota_id: undefined,
  model_quota_id: undefined,
  rule_enabled: false,
  concurrency_limit_enabled: false,
  concurrency_limit: 1,
  rpm_limit_enabled: false,
  rpm_limit: 1,
  tpm_limit_enabled: false,
  tpm_limit: 1000,
});

// 统一收敛规则字段类型，避免输入框返回字符串时污染提交载荷。
export const normalizeRateLimitRules = (rules = []) => {
  const parseOptionalPositiveInt = (value) => {
    const parsedValue = parseInt(value, 10);
    return Number.isInteger(parsedValue) && parsedValue > 0
      ? parsedValue
      : undefined;
  };
  return (Array.isArray(rules) ? rules : []).map((rule) => ({
    model_name: `${rule?.model_name || ''}`.trim(),
    quota_id: parseOptionalPositiveInt(rule?.quota_id),
    model_quota_id: parseOptionalPositiveInt(rule?.model_quota_id),
    // rule_enabled 仅用于前端控制该规则是否展开与参与提交；历史数据未携带该字段时按已启用维度自动回填。
    rule_enabled:
      rule?.rule_enabled !== undefined
        ? !!rule.rule_enabled
        : !!(
            rule?.concurrency_limit_enabled ||
            rule?.rpm_limit_enabled ||
            rule?.tpm_limit_enabled
          ),
    concurrency_limit_enabled: !!rule?.concurrency_limit_enabled,
    concurrency_limit: Math.max(1, parseInt(rule?.concurrency_limit, 10) || 1),
    rpm_limit_enabled: !!rule?.rpm_limit_enabled,
    rpm_limit: Math.max(1, parseInt(rule?.rpm_limit, 10) || 1),
    tpm_limit_enabled: !!rule?.tpm_limit_enabled,
    tpm_limit: Math.max(1, parseInt(rule?.tpm_limit, 10) || 1),
  }));
};

// 提交给表单与后端时去掉纯前端状态字段，避免把卡片展开态误带入请求载荷。
export const serializeRateLimitRules = (rules = []) =>
  normalizeRateLimitRules(rules).map(
    ({ rule_enabled: _ruleEnabled, ...rule }) => rule,
  );

// buildRateLimitRulesFromModelLimits 让规则块严格跟随“模型限制列表”生成，同时尽量保留已填写的规则值。
export const buildRateLimitRulesFromModelLimits = (
  modelLimits = [],
  rules = [],
) => {
  const normalizedModelLimits = Array.from(
    new Set(
      (Array.isArray(modelLimits) ? modelLimits : [])
        .map((modelName) => `${modelName || ''}`.trim())
        .filter(Boolean),
    ),
  );
  const normalizedRules = normalizeRateLimitRules(rules);
  const ruleMap = new Map(
    normalizedRules
      .filter((rule) => rule.model_name)
      .map((rule) => [rule.model_name, rule]),
  );
  return normalizedModelLimits.map(
    (modelName) =>
      ruleMap.get(modelName) || {
        ...createEmptyRateLimitRule(),
        model_name: modelName,
      },
  );
};

// 每条规则至少启用一个维度，避免生成“空规则”进入后端。
export const hasEnabledRateLimitDimension = (rule) => {
  return !!(
    rule?.concurrency_limit_enabled ||
    rule?.rpm_limit_enabled ||
    rule?.tpm_limit_enabled
  );
};

// sanitizeTokenModelConfig 仅规范字段类型，不按当前可用模型清理历史配置。
export const sanitizeTokenModelConfig = ({
  modelLimits = [],
  rateLimitRules = [],
}) => {
  return {
    // 渠道侧下线模型只影响可选项展示，保存其他字段时不能静默删掉既有限流账本配置。
    sanitizedModelLimits: Array.isArray(modelLimits) ? modelLimits : [],
    sanitizedRateLimitRules: normalizeRateLimitRules(rateLimitRules),
    removedModelNames: [],
  };
};

// buildModelQuotaCandidateKey 按分组和模型名生成候选缓存键，避免重复请求相同候选。
export const buildModelQuotaCandidateKey = (groupValue = '', modelName = '') =>
  `${`${groupValue || ''}`.trim()}\x00${`${modelName || ''}`.trim()}`;

// findSelectedQuotaCandidate 在当前模型候选中定位一级“关联配额池”选择项。
export const findSelectedQuotaCandidate = (candidates = [], quotaId) =>
  (Array.isArray(candidates) ? candidates : []).find(
    (candidate) => candidate?.quota_id === quotaId,
  );

// findSelectedQuotaMember 在共享池候选中定位二级共享池子项选择项。
export const findSelectedQuotaMember = (candidate, modelQuotaId) =>
  (Array.isArray(candidate?.members) ? candidate.members : []).find(
    (member) => member?.model_quota_id === modelQuotaId,
  );

// getCandidateAutoMatchMembers 返回候选中与当前模型/分组匹配的模型项，用于自动回填。
export const getCandidateAutoMatchMembers = (
  candidate,
  groupValue,
  modelName,
) => {
  const trimmedGroup = `${groupValue || ''}`.trim();
  const trimmedModelName = `${modelName || ''}`.trim();
  if (!candidate || !trimmedModelName) {
    return [];
  }
  if (candidate.quota_type !== 'shared_pool') {
    if (candidate.model_name !== trimmedModelName) {
      return [];
    }
    if (trimmedGroup && candidate.group !== trimmedGroup) {
      return [];
    }
    return [{ group: candidate.group, model_name: candidate.model_name }];
  }
  return (Array.isArray(candidate.members) ? candidate.members : []).filter(
    (member) =>
      member?.model_name === trimmedModelName &&
      (!trimmedGroup || member?.group === trimmedGroup),
  );
};

// findAutoSelectedQuotaCandidate 按 spec 的“可唯一定位才自动回填”规则选出一级候选。
export const findAutoSelectedQuotaCandidate = (
  candidates,
  groupValue,
  modelName,
) => {
  const matchedCandidates = (
    Array.isArray(candidates) ? candidates : []
  ).filter(
    (candidate) =>
      getCandidateAutoMatchMembers(candidate, groupValue, modelName).length > 0,
  );
  if (matchedCandidates.length !== 1) {
    return null;
  }
  if (`${groupValue || ''}`.trim()) {
    return matchedCandidates[0];
  }
  const matchedGroups = new Set();
  getCandidateAutoMatchMembers(
    matchedCandidates[0],
    groupValue,
    modelName,
  ).forEach((member) => {
    if (member?.group) {
      matchedGroups.add(member.group);
    }
  });
  return matchedGroups.size === 1 ? matchedCandidates[0] : null;
};

// buildQuotaDimensionCapability 根据当前选中的配额池生成维度可用性，未选中时默认全部不可用。
export const buildQuotaDimensionCapability = (candidate) => ({
  rpm_configured: !!candidate?.rpm,
  tpm_configured: !!candidate?.tpm,
  concurrency_configured: !!candidate?.concurrency,
});

// parseQuotaRemainValue 统一把剩余额度字段转成可比较数值，未配置时返回 null 表示跳过额度比较。
export const parseQuotaRemainValue = (value) => {
  if (value === null || value === undefined || value === '') {
    return null;
  }
  const parsedValue = Number(value);
  return Number.isFinite(parsedValue) ? parsedValue : null;
};

// getRuleLimitValue 只在维度启用时读取正数限流值，供额度回补计算复用。
export const getRuleLimitValue = (rule, valueKey, enabledKey) => {
  if (!rule?.[enabledKey]) {
    return 0;
  }
  const parsedValue = Number(rule?.[valueKey]);
  return Number.isFinite(parsedValue) && parsedValue > 0 ? parsedValue : 0;
};

// getExistingAllocationCredit 编辑已有规则时，把同一配额池上本 token 原占用额度计回可用余额。
export const getExistingAllocationCredit = (
  initialRules,
  nextRule,
  selectedCandidate,
  valueKey,
  enabledKey,
) => {
  if (!selectedCandidate || !nextRule?.quota_id) {
    return 0;
  }
  const previousRule = (Array.isArray(initialRules) ? initialRules : []).find(
    (rule) => rule?.model_name === nextRule.model_name,
  );
  if (!previousRule || previousRule.quota_id !== nextRule.quota_id) {
    return 0;
  }
  return getRuleLimitValue(previousRule, valueKey, enabledKey);
};

// sanitizeRuleEnabledState 按当前选中配额池能力裁剪开关，避免残留非法启用状态。
export const sanitizeRuleEnabledState = (rule, capability) => ({
  concurrency_limit_enabled: capability?.concurrency_configured
    ? !!rule?.concurrency_limit_enabled
    : false,
  rpm_limit_enabled: capability?.rpm_configured
    ? !!rule?.rpm_limit_enabled
    : false,
  tpm_limit_enabled: capability?.tpm_configured
    ? !!rule?.tpm_limit_enabled
    : false,
});

// findAutoSelectedSharedPoolMember 优先按“分组 + 模型名”自动定位共享池子项；未选分组时回退到“模型名唯一”。
export const findAutoSelectedSharedPoolMember = (
  candidate,
  groupValue,
  modelName,
) => {
  const members = Array.isArray(candidate?.members) ? candidate.members : [];
  const trimmedGroup = `${groupValue || ''}`.trim();
  const trimmedModelName = `${modelName || ''}`.trim();
  if (!trimmedModelName) {
    return null;
  }
  if (trimmedGroup) {
    const exactMatches = members.filter(
      (member) =>
        member?.group === trimmedGroup &&
        member?.model_name === trimmedModelName,
    );
    if (exactMatches.length === 1) {
      return exactMatches[0];
    }
  }
  const modelMatches = members.filter(
    (member) => member?.model_name === trimmedModelName,
  );
  return modelMatches.length === 1 ? modelMatches[0] : null;
};

// buildModelQuotaCandidateLabel 按 spec 约定输出一级候选展示文案。
export const buildModelQuotaCandidateLabel = (candidate, t) => {
  if (!candidate) {
    return '';
  }
  const remainConcurrencyText =
    candidate.remain_concurrency === null ||
    candidate.remain_concurrency === undefined
      ? t('未配置')
      : candidate.remain_concurrency;
  const remainRPMText =
    candidate.remain_rpm === null || candidate.remain_rpm === undefined
      ? t('未配置')
      : candidate.remain_rpm;
  const remainTPMText =
    candidate.remain_tpm === null || candidate.remain_tpm === undefined
      ? t('未配置')
      : candidate.remain_tpm;
  if (candidate.quota_type === 'shared_pool') {
    return `${candidate.quota_id} - ${candidate.quota_name} - ${t(
      '剩余并发数',
    )}: ${remainConcurrencyText} - ${t('剩余 RPM')}: ${remainRPMText} - ${t(
      '剩余 TPM',
    )}: ${remainTPMText}`;
  }
  return `${candidate.quota_id} - ${candidate.quota_name} - ${candidate.group} - ${t(
    '剩余并发数',
  )}: ${remainConcurrencyText} - ${t('剩余 RPM')}: ${remainRPMText} - ${t(
    '剩余 TPM',
  )}: ${remainTPMText}`;
};

// buildSharedPoolMemberLabel 按 spec 约定输出二级共享池子项展示文案。
export const buildSharedPoolMemberLabel = (member) =>
  `${member?.model_quota_id} - ${member?.model_name || ''}`;

// getCandidateMatchWeight 为单个普通模型项或共享池子项计算排序权重，分组和模型都匹配时优先。
const getCandidateMatchWeight = (quota, groupValue, modelName) => {
  const trimmedGroup = `${groupValue || ''}`.trim();
  const trimmedModelName = `${modelName || ''}`.trim();
  if (!quota || `${quota.model_name || ''}`.trim() !== trimmedModelName) {
    return 2;
  }
  if (trimmedGroup && `${quota.group || ''}`.trim() === trimmedGroup) {
    return 0;
  }
  if (!trimmedGroup) {
    return 0;
  }
  return 1;
};

// getCandidateWeight 把共享池内最匹配的子项权重提升到一级候选，保证共享池排序符合当前模型。
const getCandidateWeight = (candidate, groupValue, modelName) => {
  if (candidate?.quota_type !== 'shared_pool') {
    return getCandidateMatchWeight(candidate, groupValue, modelName);
  }
  const members = Array.isArray(candidate.members) ? candidate.members : [];
  return members.reduce(
    (minWeight, member) =>
      Math.min(
        minWeight,
        getCandidateMatchWeight(member, groupValue, modelName),
      ),
    2,
  );
};

// getCandidateTypeWeight 在匹配程度相同的情况下优先展示普通模型项，再展示共享池。
const getCandidateTypeWeight = (candidate) =>
  candidate?.quota_type === 'normal' ? 0 : 1;

// 后端候选接口为了支持手动选择返回全量候选；前端按当前模型重新排序即可复用同一响应。
export const sortModelQuotaCandidatesForModel = (
  candidates = [],
  groupValue = '',
  modelName = '',
) =>
  (Array.isArray(candidates) ? [...candidates] : []).sort((left, right) => {
    const leftWeight = getCandidateWeight(left, groupValue, modelName);
    const rightWeight = getCandidateWeight(right, groupValue, modelName);
    if (leftWeight !== rightWeight) {
      return leftWeight - rightWeight;
    }
    const leftTypeWeight = getCandidateTypeWeight(left);
    const rightTypeWeight = getCandidateTypeWeight(right);
    if (leftTypeWeight !== rightTypeWeight) {
      return leftTypeWeight - rightTypeWeight;
    }
    return (left?.quota_id || 0) - (right?.quota_id || 0);
  });

// buildModelQuotaCandidateMap 按模型名生成候选列表缓存，避免渲染每张规则卡片时重复排序。
export const buildModelQuotaCandidateMap = (
  candidates = [],
  groupValue = '',
  modelNames = [],
) => {
  const candidateMap = {};
  (Array.isArray(modelNames) ? modelNames : []).forEach((modelName) => {
    candidateMap[buildModelQuotaCandidateKey(groupValue, modelName)] =
      sortModelQuotaCandidatesForModel(candidates, groupValue, modelName);
  });
  return candidateMap;
};
