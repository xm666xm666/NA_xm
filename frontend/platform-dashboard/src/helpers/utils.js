import { toast } from 'react-toastify';

export function isAdmin() {
  const rawUser = localStorage.getItem('user');
  if (!rawUser) return false;
  try {
    return Number(JSON.parse(rawUser)?.role) >= 10;
  } catch {
    return false;
  }
}

export async function copy(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    try {
      const textarea = document.createElement('textarea');
      textarea.value = text;
      textarea.setAttribute('readonly', '');
      textarea.style.position = 'fixed';
      textarea.style.left = '-9999px';
      document.body.appendChild(textarea);
      textarea.select();
      const copied = document.execCommand('copy');
      textarea.remove();
      return copied;
    } catch {
      return false;
    }
  }
}

export function showError(error) {
  console.error(error);
  const message = error?.response?.data?.message || error?.message || String(error);
  toast.error(`错误：${message || '未知错误'}`);
}

export function showSuccess(message) {
  toast.success(message);
}

export function timestamp2string(timestamp) {
  const date = new Date(timestamp * 1000);
  const pad = (value) => String(value).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

export function timestamp2string1(timestamp, dataExportDefaultTime = 'hour', showYear = false) {
  const date = new Date(timestamp * 1000);
  const pad = (value) => String(value).padStart(2, '0');
  let label = showYear
    ? `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
    : `${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
  if (dataExportDefaultTime === 'hour') {
    label += ` ${pad(date.getHours())}:00`;
  } else if (dataExportDefaultTime === 'week') {
    const nextWeek = new Date(timestamp * 1000 + 6 * 24 * 60 * 60 * 1000);
    const nextLabel = showYear
      ? `${nextWeek.getFullYear()}-${pad(nextWeek.getMonth() + 1)}-${pad(nextWeek.getDate())}`
      : `${pad(nextWeek.getMonth() + 1)}-${pad(nextWeek.getDate())}`;
    label += ` - ${nextLabel}`;
  }
  return label;
}

export function isDataCrossYear(timestamps) {
  if (!timestamps || timestamps.length === 0) return false;
  const years = new Set(timestamps.map((timestamp) => new Date(timestamp * 1000).getFullYear()));
  return years.size > 1;
}

export const formatDateString = (date) => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

export const getRelativeTime = (publishDate) => {
  if (!publishDate) return '';
  const publish = new Date(publishDate);
  if (Number.isNaN(publish.getTime())) return publishDate;
  const difference = Date.now() - publish.getTime();
  if (difference < 0) return formatDateString(publish);
  const seconds = Math.floor(difference / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);
  const weeks = Math.floor(days / 7);
  const months = Math.floor(days / 30);
  const years = Math.floor(days / 365);
  if (seconds < 60) return '刚刚';
  if (minutes < 60) return `${minutes} 分钟前`;
  if (hours < 24) return `${hours} 小时前`;
  if (days < 7) return `${days} 天前`;
  if (weeks < 4) return `${weeks} 周前`;
  if (months < 12) return `${months} 个月前`;
  if (years < 2) return '1 年前';
  return formatDateString(publish);
};
