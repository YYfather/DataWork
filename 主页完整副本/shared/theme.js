/**
 * Shared Theme - 主题切换功能
 */

// ==================== 主题管理 ====================
const ThemeManager = {
    // 主题键名
    STORAGE_KEY: 'theme',
    
    // 获取当前主题
    getTheme() {
        return document.documentElement.getAttribute('data-theme') || 'light';
    },
    
    // 设置主题
    setTheme(theme) {
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem(this.STORAGE_KEY, theme);
        this.updateThemeIcon();
        this.dispatchThemeChange(theme);
    },
    
    // 切换主题
    toggle() {
        const current = this.getTheme();
        const next = current === 'dark' ? 'light' : 'dark';
        this.setTheme(next);
    },
    
    // 初始化主题
    init() {
        // 从本地存储获取
        const saved = localStorage.getItem(this.STORAGE_KEY);
        
        // 如果有保存的主题，使用它
        if (saved) {
            this.setTheme(saved);
            return;
        }
        
        // 否则，检查系统偏好
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        this.setTheme(prefersDark ? 'dark' : 'light');
        
        // 监听系统主题变化
        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
            // 只有在没有手动设置主题时才跟随系统
            if (!localStorage.getItem(this.STORAGE_KEY)) {
                this.setTheme(e.matches ? 'dark' : 'light');
            }
        });
    },
    
    // 更新主题图标
    updateThemeIcon() {
        const themeBtns = document.querySelectorAll('.theme-btn, [onclick*="toggleTheme"]');
        const isDark = this.getTheme() === 'dark';
        
        themeBtns.forEach(btn => {
            if (btn.classList.contains('theme-btn')) {
                btn.textContent = isDark ? '☀️' : '🌙';
                btn.setAttribute('aria-label', isDark ? '切换到浅色模式' : '切换到深色模式');
            }
        });
    },
    
    // 派发主题变化事件
    dispatchThemeChange(theme) {
        const event = new CustomEvent('themechange', {
            detail: { theme },
            bubbles: true
        });
        document.dispatchEvent(event);
    },
    
    // 重置主题（清除手动设置）
    reset() {
        localStorage.removeItem(this.STORAGE_KEY);
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        this.setTheme(prefersDark ? 'dark' : 'light');
    }
};

// ==================== 全局函数 ====================
/**
 * 切换主题（兼容旧代码）
 */
function toggleTheme() {
    ThemeManager.toggle();
}

/**
 * 初始化主题（兼容旧代码）
 */
function initTheme() {
    ThemeManager.init();
}

// ==================== 自动初始化 ====================
// 在 DOM 加载完成后初始化主题
if (typeof onDOMReady === 'function') {
    onDOMReady(() => ThemeManager.init());
} else {
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => ThemeManager.init());
    } else {
        ThemeManager.init();
    }
}

// ==================== 导出 ====================
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        ThemeManager,
        toggleTheme,
        initTheme
    };
}
