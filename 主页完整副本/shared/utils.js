/**
 * Shared Utilities - 通用工具函数
 */

// ==================== XSS 防护 ====================
/**
 * 转义 HTML 特殊字符，防止 XSS 攻击
 * @param {string} unsafe - 未转义的字符串
 * @returns {string} 转义后的字符串
 */
function escapeHtml(unsafe) {
    if (typeof unsafe !== 'string') return '';
    return unsafe
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

// 别名，方便使用
const esc = escapeHtml;

/**
 * 转义 HTML 属性值，防止 XSS 攻击
 * @param {string} s - 未转义的字符串
 * @returns {string} 转义后的字符串，可安全用于 HTML 属性
 */
function escAttr(s) {
    if (!s) return '';
    return escapeHtml(s).replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

// ==================== Toast 通知 ====================
/**
 * 显示 Toast 通知
 * @param {string} message - 通知消息
 * @param {string} type - 通知类型 ('success' | 'error' | 'info')
 * @param {number} duration - 显示时长（毫秒）
 */
function showToast(message, type = 'info', duration = 3000) {
    // 获取或创建容器
    let container = document.querySelector('.toast-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'toast-container';
        container.setAttribute('aria-live', 'polite');
        container.setAttribute('aria-atomic', 'true');
        document.body.appendChild(container);
    }
    
    // 创建 Toast 元素
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    toast.setAttribute('role', 'alert');
    
    // 添加到容器
    container.appendChild(toast);
    
    // 自动移除
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

// ==================== 加载状态 ====================
/**
 * 显示加载状态
 * @param {HTMLElement} container - 容器元素
 * @param {string} message - 加载消息
 */
function showLoading(container, message = '加载中...') {
    if (!container) return;
    container.innerHTML = `
        <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;padding:40px 20px;text-align:center">
            <div class="spinner" style="margin-bottom:16px"></div>
            <div style="color:var(--c-text2);font-size:14px">${escapeHtml(message)}</div>
        </div>
    `;
}

/**
 * 显示错误状态
 * @param {HTMLElement} container - 容器元素
 * @param {string} message - 错误消息
 * @param {Function} retryFn - 重试函数（可选）
 */
function showError(container, message, retryFn = null) {
    if (!container) return;
    container.innerHTML = `
        <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;padding:40px 20px;text-align:center">
            <div style="font-size:48px;margin-bottom:16px">⚠️</div>
            <div style="color:var(--c-text2);font-size:14px;margin-bottom:16px">${escapeHtml(message)}</div>
            ${retryFn ? '<button class="btn btn-primary" onclick="this.parentElement.remove();(' + retryFn.toString() + ')()">重试</button>' : ''}
        </div>
    `;
}

/**
 * 显示空状态
 * @param {HTMLElement} container - 容器元素
 * @param {string} message - 空状态消息
 * @param {string} icon - 图标（可选）
 */
function showEmpty(container, message = '暂无数据', icon = '📭') {
    if (!container) return;
    container.innerHTML = `
        <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;padding:40px 20px;text-align:center">
            <div style="font-size:48px;margin-bottom:16px">${icon}</div>
            <div style="color:var(--c-text2);font-size:14px">${escapeHtml(message)}</div>
        </div>
    `;
}

// ==================== 本地存储 ====================
/**
 * 安全地获取本地存储
 * @param {string} key - 存储键
 * @param {*} defaultValue - 默认值
 * @returns {*} 存储的值
 */
function getStorage(key, defaultValue = null) {
    try {
        const value = localStorage.getItem(key);
        return value ? JSON.parse(value) : defaultValue;
    } catch {
        return defaultValue;
    }
}

/**
 * 安全地设置本地存储
 * @param {string} key - 存储键
 * @param {*} value - 存储的值
 */
function setStorage(key, value) {
    try {
        localStorage.setItem(key, JSON.stringify(value));
    } catch (e) {
        console.error('Failed to save to localStorage:', e);
    }
}

/**
 * 安全地移除本地存储
 * @param {string} key - 存储键
 */
function removeStorage(key) {
    try {
        localStorage.removeItem(key);
    } catch (e) {
        console.error('Failed to remove from localStorage:', e);
    }
}

// ==================== 防抖和节流 ====================
/**
 * 防抖函数
 * @param {Function} func - 要防抖的函数
 * @param {number} wait - 等待时间（毫秒）
 * @returns {Function} 防抖后的函数
 */
function debounce(func, wait = 300) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

/**
 * 节流函数
 * @param {Function} func - 要节流的函数
 * @param {number} limit - 限制时间（毫秒）
 * @returns {Function} 节流后的函数
 */
function throttle(func, limit) {
    let inThrottle;
    return function executedFunction(...args) {
        if (!inThrottle) {
            func(...args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
}

// ==================== 日期和时间 ====================
/**
 * 格式化日期
 * @param {Date|string|number} date - 日期
 * @param {string} format - 格式 ('YYYY-MM-DD' | 'YYYY-MM-DD HH:mm' | 'relative')
 * @returns {string} 格式化后的日期
 */
function formatDate(date, format = 'YYYY-MM-DD') {
    const d = new Date(date);
    
    if (isNaN(d.getTime())) {
        return '无效日期';
    }
    
    if (format === 'relative') {
        return getRelativeTime(d);
    }
    
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    const hours = String(d.getHours()).padStart(2, '0');
    const minutes = String(d.getMinutes()).padStart(2, '0');
    
    switch (format) {
        case 'YYYY-MM-DD':
            return `${year}-${month}-${day}`;
        case 'YYYY-MM-DD HH:mm':
            return `${year}-${month}-${day} ${hours}:${minutes}`;
        default:
            return `${year}-${month}-${day}`;
    }
}

/**
 * 获取相对时间
 * @param {Date} date - 日期
 * @returns {string} 相对时间描述
 */
function getRelativeTime(date) {
    const now = new Date();
    const diff = now - date;
    const seconds = Math.floor(diff / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);
    const days = Math.floor(hours / 24);
    
    if (seconds < 60) return '刚刚';
    if (minutes < 60) return `${minutes}分钟前`;
    if (hours < 24) return `${hours}小时前`;
    if (days < 7) return `${days}天前`;
    if (days < 30) return `${Math.floor(days / 7)}周前`;
    if (days < 365) return `${Math.floor(days / 30)}个月前`;
    return `${Math.floor(days / 365)}年前`;
}

// ==================== 数字和格式化 ====================
/**
 * 格式化数字（添加千分位分隔符）
 * @param {number} num - 数字
 * @returns {string} 格式化后的数字
 */
function formatNumber(num) {
    return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

/**
 * 格式化文件大小
 * @param {number} bytes - 字节数
 * @returns {string} 格式化后的文件大小
 */
function formatFileSize(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

// ==================== DOM 操作 ====================
/**
 * 等待 DOM 加载完成
 * @param {Function} callback - 回调函数
 */
function onDOMReady(callback) {
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', callback);
    } else {
        callback();
    }
}

/**
 * 安全地获取元素
 * @param {string} selector - CSS 选择器
 * @returns {HTMLElement|null} 元素
 */
function $(selector) {
    return document.querySelector(selector);
}

/**
 * 安全地获取多个元素
 * @param {string} selector - CSS 选择器
 * @returns {NodeList} 元素列表
 */
function $$(selector) {
    return document.querySelectorAll(selector);
}

// ==================== URL 和路径 ====================
/**
 * 获取 URL 参数
 * @param {string} name - 参数名
 * @returns {string|null} 参数值
 */
function getUrlParam(name) {
    const urlParams = new URLSearchParams(window.location.search);
    return urlParams.get(name);
}

/**
 * 获取 API 基础路径
 * @returns {string} API 基础路径
 */
function getApiBase() {
    let p = location.pathname;
    if (!p.endsWith('/')) {
        const seg = p.split('/').pop() || '';
        if (seg.includes('.')) {
            p = p.substring(0, p.lastIndexOf('/') + 1);
        } else {
            p += '/';
        }
    }
    return location.origin + p;
}

// ==================== 复制到剪贴板 ====================
/**
 * 复制文本到剪贴板
 * @param {string} text - 要复制的文本
 * @returns {Promise<boolean>} 是否成功
 */
async function copyToClipboard(text) {
    try {
        await navigator.clipboard.writeText(text);
        showToast('已复制到剪贴板', 'success', 2000);
        return true;
    } catch {
        // 降级方案
        const textarea = document.createElement('textarea');
        textarea.value = text;
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
        document.body.appendChild(textarea);
        textarea.select();
        try {
            document.execCommand('copy');
            showToast('已复制到剪贴板', 'success', 2000);
            return true;
        } catch {
            showToast('复制失败', 'error');
            return false;
        } finally {
            document.body.removeChild(textarea);
        }
    }
}

// ==================== 导出 ====================
// 如果在模块环境中，导出函数
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        escapeHtml,
        esc,
        showToast,
        showLoading,
        showError,
        showEmpty,
        getStorage,
        setStorage,
        removeStorage,
        debounce,
        throttle,
        formatDate,
        getRelativeTime,
        formatNumber,
        formatFileSize,
        onDOMReady,
        $,
        $$,
        getUrlParam,
        getApiBase,
        copyToClipboard
    };
}
