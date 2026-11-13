export function setStatusData(data) {
  const status = data && typeof data === 'object' ? data : {};
  localStorage.setItem('status', JSON.stringify(status));
  localStorage.setItem('system_name', status.system_name || 'New API');
  localStorage.setItem('logo', status.logo || '');
  localStorage.setItem('footer_html', status.footer_html || '');
  localStorage.setItem('display_in_currency', status.display_in_currency ?? true);
  localStorage.setItem('quota_display_type', status.quota_display_type || 'USD');
  const quotaPerUnit = Number(status.quota_per_unit);
  localStorage.setItem('quota_per_unit', String(quotaPerUnit > 0 ? quotaPerUnit : 500000));
  if (['hour', 'day', 'week'].includes(status.data_export_default_time)) {
    localStorage.setItem('data_export_default_time', status.data_export_default_time);
  }
}

export function setUserData(data) {
  localStorage.setItem('user', JSON.stringify(data));
}
