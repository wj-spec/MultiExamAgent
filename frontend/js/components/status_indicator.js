/**
 * status_indicator.js
 * 
 * 状态指示器组件 - 实现设计文档中的「微动画」效果
 * 
 * 设计文档要求：
 * - 大量使用微动画表现"正在思考"、"正在爬取"、"正在计算"
 * - 让长时任务的等待过程变得"好看且让人觉得它很努力"
 * 
 * 核心功能：
 * 1. 多种状态动画（思考、搜索、计算、生成等）
 * 2. 进度指示
 * 3. 可嵌入到任意容器
 */

const StatusIndicator = (() => {
    'use strict';

    // ==================== 状态类型 ====================
    const STATUS_TYPES = {
        thinking: {
            icon: 'brain',
            text: '正在思考...',
            color: '#a78bfa'
        },
        searching: {
            icon: 'search',
            text: '正在搜索...',
            color: '#3b82f6'
        },
        calculating: {
            icon: 'calculator',
            text: '正在计算...',
            color: '#10b981'
        },
        generating: {
            icon: 'sparkle',
            text: '正在生成...',
            color: '#f59e0b'
        },
        validating: {
            icon: 'check',
            text: '正在验证...',
            color: '#06b6d4'
        },
        idle: {
            icon: 'circle',
            text: '就绪',
            color: '#6b7280'
        }
    };

    // ==================== 状态 ====================
    let _containerEl = null;
    let _currentStatus = 'idle';
    let _progress = 0;
    let _animationFrame = null;

    // ==================== 初始化 ====================

    /**
     * 初始化状态指示器
     * @param {string} containerId - 容器元素ID
     */
    function init(containerId) {
        _containerEl = document.getElementById(containerId);
        if (!_containerEl) {
            console.warn('[StatusIndicator] 容器元素不存在:', containerId);
            return;
        }

        _render('idle');
    }

    // ==================== 核心方法 ====================

    /**
     * 设置状态
     * @param {string} status - 状态类型: thinking | searching | calculating | generating | validating | idle
     * @param {string} customText - 自定义文本（可选）
     */
    function setStatus(status, customText = null) {
        _currentStatus = status;
        _render(status, customText);
    }

    /**
     * 设置进度
     * @param {number} progress - 进度值 (0-100)
     */
    function setProgress(progress) {
        _progress = Math.min(100, Math.max(0, progress));
        _updateProgressBar();
    }

    /**
     * 显示状态指示器
     */
    function show() {
        if (_containerEl) {
            _containerEl.style.display = 'block';
        }
    }

    /**
     * 隐藏状态指示器
     */
    function hide() {
        if (_containerEl) {
            _containerEl.style.display = 'none';
        }
    }

    /**
     * 显示带进度条的状态
     * @param {string} status - 状态类型
     * @param {number} progress - 进度值
     * @param {string} text - 状态文本
     */
    function showWithProgress(status, progress, text = null) {
        setStatus(status, text);
        setProgress(progress);
        show();
    }

    /**
     * 创建内联状态指示器（用于嵌入其他组件）
     * @param {string} status - 状态类型
     * @param {string} text - 状态文本
     * @returns {string} HTML 字符串
     */
    function createInline(status, text = null) {
        const config = STATUS_TYPES[status] || STATUS_TYPES.idle;
        return `
      <span class="status-indicator-inline status-${status}">
        <span class="status-dot" style="background: ${config.color}"></span>
        <span class="status-text">${text || config.text}</span>
      </span>
    `;
    }

    /**
     * 创建骨架屏加载效果
     * @param {number} count - 骨架项数量
     * @returns {string} HTML 字符串
     */
    function createSkeleton(count = 3) {
        let html = '<div class="skeleton-container">';
        for (let i = 0; i < count; i++) {
            html += `
        <div class="skeleton-item" style="animation-delay: ${i * 0.1}s">
          <div class="skeleton-avatar"></div>
          <div class="skeleton-content">
            <div class="skeleton-title"></div>
            <div class="skeleton-text"></div>
            <div class="skeleton-text short"></div>
          </div>
        </div>
      `;
        }
        html += '</div>';
        return html;
    }

    /**
     * 创建进度矩阵（用于显示多任务进度）
     * @param {number} total - 总任务数
     * @param {Array} completed - 已完成任务索引列表
     * @param {Array} running - 正在执行的任务索引列表
     * @returns {string} HTML 字符串
     */
    function createProgressMatrix(total, completed = [], running = []) {
        let html = '<div class="progress-matrix">';
        for (let i = 0; i < total; i++) {
            const isCompleted = completed.includes(i);
            const isRunning = running.includes(i);
            const statusClass = isCompleted ? 'completed' : isRunning ? 'running' : 'pending';
            html += `
        <div class="matrix-cell ${statusClass}" title="任务 ${i + 1}">
          ${isCompleted ? '✓' : isRunning ? '<span class="cell-spinner"></span>' : i + 1}
        </div>
      `;
        }
        html += '</div>';
        return html;
    }

    // ==================== 渲染方法 ====================

    function _render(status, customText = null) {
        if (!_containerEl) return;

        const config = STATUS_TYPES[status] || STATUS_TYPES.idle;

        _containerEl.innerHTML = `
      <div class="status-indicator status-${status}">
        <div class="status-icon-container">
          ${_getIconSVG(config.icon, config.color)}
          <div class="status-ripple" style="border-color: ${config.color}"></div>
        </div>
        <div class="status-content">
          <div class="status-text">${customText || config.text}</div>
          <div class="status-progress-bar">
            <div class="status-progress-fill" style="width: ${_progress}%"></div>
          </div>
        </div>
      </div>
    `;
    }

    function _updateProgressBar() {
        const fill = _containerEl?.querySelector('.status-progress-fill');
        if (fill) {
            fill.style.width = `${_progress}%`;
        }
    }

    function _getIconSVG(icon, color) {
        const icons = {
            brain: `<svg class="status-icon pulsing" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="${color}" stroke-width="2">
        <path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96.44 2.5 2.5 0 0 1-2.96-3.08 3 3 0 0 1-.34-5.58 2.5 2.5 0 0 1 1.32-4.24 2.5 2.5 0 0 1 4.44-1.54"></path>
        <path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96.44 2.5 2.5 0 0 0 2.96-3.08 3 3 0 0 0 .34-5.58 2.5 2.5 0 0 0-1.32-4.24 2.5 2.5 0 0 0-4.44-1.54"></path>
      </svg>`,
            search: `<svg class="status-icon rotating" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="${color}" stroke-width="2">
        <circle cx="11" cy="11" r="8"></circle>
        <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
      </svg>`,
            calculator: `<svg class="status-icon pulsing" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="${color}" stroke-width="2">
        <rect x="4" y="2" width="16" height="20" rx="2"></rect>
        <line x1="8" y1="6" x2="16" y2="6"></line>
        <line x1="8" y1="10" x2="8" y2="10.01"></line>
        <line x1="12" y1="10" x2="12" y2="10.01"></line>
        <line x1="16" y1="10" x2="16" y2="10.01"></line>
        <line x1="8" y1="14" x2="8" y2="14.01"></line>
        <line x1="12" y1="14" x2="12" y2="14.01"></line>
        <line x1="16" y1="14" x2="16" y2="14.01"></line>
        <line x1="8" y1="18" x2="8" y2="18.01"></line>
        <line x1="12" y1="18" x2="12" y2="18.01"></line>
        <line x1="16" y1="18" x2="16" y2="18.01"></line>
      </svg>`,
            sparkle: `<svg class="status-icon sparkling" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="${color}" stroke-width="2">
        <path d="M12 3l1.912 5.813a2 2 0 0 0 1.275 1.275L21 12l-5.813 1.912a2 2 0 0 0-1.275 1.275L12 21l-1.912-5.813a2 2 0 0 0-1.275-1.275L3 12l5.813-1.912a2 2 0 0 0 1.275-1.275L12 3z"></path>
      </svg>`,
            check: `<svg class="status-icon pulsing" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="${color}" stroke-width="2">
        <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
        <polyline points="22 4 12 14.01 9 11.01"></polyline>
      </svg>`,
            circle: `<svg class="status-icon" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="${color}" stroke-width="2">
        <circle cx="12" cy="12" r="10"></circle>
      </svg>`
        };

        return icons[icon] || icons.circle;
    }

    // ==================== 公共 API ====================

    return {
        init,
        setStatus,
        setProgress,
        show,
        hide,
        showWithProgress,
        createInline,
        createSkeleton,
        createProgressMatrix,
        STATUS_TYPES
    };
})();

// 导出全局
window.StatusIndicator = StatusIndicator;
