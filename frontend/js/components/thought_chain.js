/**
 * thought_chain.js
 * 
 * 思考链可视化组件 - 实现设计文档中的「Agent Activity Log / Thought Chain」
 * 
 * 核心功能：
 * 1. 实时展示 Agent 内在思考（Thought）
 * 2. 展示工具调用和执行步骤（Action）
 * 3. 展示观察结果（Observation）
 * 4. 结构化的时间线展示
 * 5. 步骤折叠/展开
 * 6. 进度指示器
 */

const ThoughtChain = (() => {
    'use strict';

    // ==================== 状态 ====================
    let _containerEl = null;
    let _steps = [];           // 所有步骤
    let _currentStepId = null; // 当前执行的步骤
    let _isCollapsed = {};     // 折叠状态

    // ==================== 初始化 ====================

    /**
     * 初始化思考链组件
     * @param {string} containerId - 容器元素ID
     */
    function init(containerId) {
        _containerEl = document.getElementById(containerId);
        if (!_containerEl) {
            console.warn('[ThoughtChain] 容器元素不存在:', containerId);
            return;
        }

        _steps = [];
        _currentStepId = null;
        _isCollapsed = {};

        _render();
    }

    // ==================== 核心方法 ====================

    /**
     * 添加思考步骤
     * @param {Object} step - 步骤对象
     * @param {string} step.id - 步骤ID
     * @param {string} step.type - 类型: thought | action | observation | output
     * @param {string} step.title - 标题
     * @param {string} step.content - 内容
     * @param {string} step.status - 状态: running | done | error
     * @param {string} step.parentId - 父步骤ID（用于嵌套）
     */
    function addStep(step) {
        const stepData = {
            id: step.id || `step_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
            type: step.type || 'thought',
            title: step.title || '',
            content: step.content || '',
            status: step.status || 'running',
            parentId: step.parentId || null,
            timestamp: Date.now(),
            elapsed: null,
            children: []
        };

        // 如果有父步骤，添加为子步骤
        if (stepData.parentId) {
            const parent = _findStep(stepData.parentId);
            if (parent) {
                parent.children.push(stepData);
            }
        } else {
            _steps.push(stepData);
        }

        _currentStepId = stepData.id;
        _renderStep(stepData);
        _scrollToBottom();

        return stepData.id;
    }

    /**
     * 更新步骤状态
     * @param {string} stepId - 步骤ID
     * @param {Object} update - 更新内容
     */
    function updateStep(stepId, update) {
        const step = _findStep(stepId);
        if (!step) return;

        if (update.status) step.status = update.status;
        if (update.content) step.content = update.content;
        if (update.title) step.title = update.title;
        if (update.elapsed !== undefined) step.elapsed = update.elapsed;

        _updateStepElement(step);
    }

    /**
     * 完成当前步骤
     * @param {string} stepId - 步骤ID
     * @param {string} result - 结果内容
     * @param {number} elapsedMs - 耗时（毫秒）
     */
    function completeStep(stepId, result = '', elapsedMs = null) {
        updateStep(stepId, {
            status: 'done',
            content: result,
            elapsed: elapsedMs ? `${(elapsedMs / 1000).toFixed(1)}s` : null
        });
    }

    /**
     * 标记步骤错误
     * @param {string} stepId - 步骤ID
     * @param {string} error - 错误信息
     */
    function errorStep(stepId, error = '') {
        updateStep(stepId, {
            status: 'error',
            content: error
        });
    }

    /**
     * 添加工具调用
     * @param {Object} toolCall - 工具调用信息
     */
    function addToolCall(toolCall) {
        const stepId = addStep({
            type: 'action',
            title: `调用工具: ${toolCall.name || '未知工具'}`,
            content: JSON.stringify(toolCall.arguments || {}, null, 2),
            status: 'running'
        });

        return stepId;
    }

    /**
     * 完成工具调用
     * @param {string} stepId - 步骤ID
     * @param {Object} result - 工具返回结果
     */
    function completeToolCall(stepId, result) {
        completeStep(stepId, typeof result === 'string' ? result : JSON.stringify(result, null, 2));
    }

    /**
     * 添加思考内容
     * @param {string} thought - 思考内容
     */
    function addThought(thought) {
        addStep({
            type: 'thought',
            title: '思考',
            content: thought,
            status: 'done'
        });
    }

    /**
     * 添加观察结果
     * @param {string} observation - 观察内容
     */
    function addObservation(observation) {
        addStep({
            type: 'observation',
            title: '观察结果',
            content: observation,
            status: 'done'
        });
    }

    /**
     * 添加输出结果
     * @param {string} output - 输出内容
     */
    function addOutput(output) {
        addStep({
            type: 'output',
            title: '生成结果',
            content: output,
            status: 'done'
        });
    }

    /**
     * 清空所有步骤
     */
    function clear() {
        _steps = [];
        _currentStepId = null;
        _isCollapsed = {};
        if (_containerEl) {
            _render();
        }
    }

    /**
     * 获取步骤总数
     */
    function getStepCount() {
        return _steps.length;
    }

    // ==================== 渲染方法 ====================

    function _render() {
        if (!_containerEl) return;

        _containerEl.innerHTML = `
      <div class="thought-chain-container">
        <div class="thought-chain-header">
          <div class="chain-header-title">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"></circle>
              <polyline points="12 6 12 12 16 14"></polyline>
            </svg>
            <span>执行日志</span>
          </div>
          <div class="chain-header-actions">
            <button class="chain-action-btn" id="chain-clear-btn" title="清空">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="3 6 5 6 21 6"></polyline>
                <path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"></path>
              </svg>
            </button>
            <button class="chain-action-btn" id="chain-collapse-btn" title="折叠全部">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                <line x1="9" y1="12" x2="15" y2="12"></line>
              </svg>
            </button>
          </div>
        </div>
        <div class="thought-chain-body" id="thought-chain-body">
          <div class="chain-empty-state">
            <p>等待 Agent 开始执行...</p>
          </div>
        </div>
      </div>
    `;

        _bindChainEvents();
    }

    function _bindChainEvents() {
        document.getElementById('chain-clear-btn')?.addEventListener('click', clear);

        document.getElementById('chain-collapse-btn')?.addEventListener('click', () => {
            const allCollapsed = Object.values(_isCollapsed).every(v => v);
            _steps.forEach(s => _isCollapsed[s.id] = !allCollapsed);
            _renderAllSteps();
        });
    }

    function _renderStep(step) {
        const body = document.getElementById('thought-chain-body');
        if (!body) return;

        // 移除空状态
        const emptyEl = body.querySelector('.chain-empty-state');
        if (emptyEl) emptyEl.remove();

        const stepEl = document.createElement('div');
        stepEl.className = `chain-step chain-step-${step.type} chain-step-${step.status}`;
        stepEl.id = `chain-step-${step.id}`;
        stepEl.dataset.stepId = step.id;

        stepEl.innerHTML = _getStepHTML(step);

        // 如果有父步骤，插入到父步骤内部
        if (step.parentId) {
            const parentEl = document.getElementById(`chain-step-${step.parentId}`);
            const childrenContainer = parentEl?.querySelector('.chain-children');
            if (childrenContainer) {
                childrenContainer.appendChild(stepEl);
                return;
            }
        }

        body.appendChild(stepEl);
        _bindStepEvents(stepEl, step);
    }

    function _getStepHTML(step) {
        const icon = _getStepIcon(step.type, step.status);
        const timeStr = new Date(step.timestamp).toLocaleTimeString();
        const hasChildren = step.children && step.children.length > 0;
        const isCollapsed = _isCollapsed[step.id];

        return `
      <div class="step-header">
        <div class="step-icon">${icon}</div>
        <div class="step-info">
          <div class="step-title">${step.title}</div>
          <div class="step-meta">
            <span class="step-time">${timeStr}</span>
            ${step.elapsed ? `<span class="step-elapsed">${step.elapsed}</span>` : ''}
          </div>
        </div>
        <div class="step-actions">
          ${step.content ? `
            <button class="step-toggle-btn" title="${isCollapsed ? '展开' : '折叠'}">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="${isCollapsed ? '9 18 15 12 9 6' : '6 9 12 15 18 9'}"></polyline>
              </svg>
            </button>
          ` : ''}
        </div>
      </div>
      ${step.content ? `
        <div class="step-content ${isCollapsed ? 'collapsed' : ''}">
          <pre>${_escapeHtml(step.content)}</pre>
        </div>
      ` : ''}
      ${hasChildren ? `
        <div class="chain-children ${isCollapsed ? 'collapsed' : ''}">
          ${step.children.map(child => `<div id="chain-step-${child.id}"></div>`).join('')}
        </div>
      ` : ''}
    `;
    }

    function _renderAllSteps() {
        const body = document.getElementById('thought-chain-body');
        if (!body) return;

        body.innerHTML = '';
        _steps.forEach(step => _renderStep(step));
    }

    function _updateStepElement(step) {
        const stepEl = document.getElementById(`chain-step-${step.id}`);
        if (!stepEl) return;

        // 更新类名
        stepEl.className = `chain-step chain-step-${step.type} chain-step-${step.status}`;

        // 更新内容
        stepEl.innerHTML = _getStepHTML(step);
        _bindStepEvents(stepEl, step);
    }

    function _bindStepEvents(stepEl, step) {
        const toggleBtn = stepEl.querySelector('.step-toggle-btn');
        if (toggleBtn) {
            toggleBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                _isCollapsed[step.id] = !_isCollapsed[step.id];
                _updateStepElement(step);
            });
        }
    }

    // ==================== 工具方法 ====================

    function _findStep(stepId, steps = _steps) {
        for (const step of steps) {
            if (step.id === stepId) return step;
            if (step.children && step.children.length > 0) {
                const found = _findStep(stepId, step.children);
                if (found) return found;
            }
        }
        return null;
    }

    /**
     * 根据标题查找步骤
     * @param {string} title - 步骤标题
     * @returns {Object|null} 找到的步骤对象
     */
    function findStepByTitle(title, steps = _steps) {
        for (const step of steps) {
            if (step.title === title) return step;
            if (step.children && step.children.length > 0) {
                const found = findStepByTitle(title, step.children);
                if (found) return found;
            }
        }
        return null;
    }

    function _getStepIcon(type, status) {
        const icons = {
            thought: {
                running: `<svg class="icon-spin" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#a78bfa" stroke-width="2">
          <circle cx="12" cy="12" r="10"></circle>
          <path d="M12 6v6l4 2"></path>
        </svg>`,
                done: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#a78bfa" stroke-width="2">
          <circle cx="12" cy="12" r="10"></circle>
          <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"></path>
          <line x1="12" y1="17" x2="12.01" y2="17"></line>
        </svg>`,
                error: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2">
          <circle cx="12" cy="12" r="10"></circle>
          <line x1="15" y1="9" x2="9" y2="15"></line>
          <line x1="9" y1="9" x2="15" y2="15"></line>
        </svg>`
            },
            action: {
                running: `<svg class="icon-spin" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" stroke-width="2">
          <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"></path>
        </svg>`,
                done: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" stroke-width="2">
          <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"></path>
        </svg>`,
                error: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2">
          <circle cx="12" cy="12" r="10"></circle>
          <line x1="15" y1="9" x2="9" y2="15"></line>
          <line x1="9" y1="9" x2="15" y2="15"></line>
        </svg>`
            },
            observation: {
                running: `<svg class="icon-spin" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2">
          <circle cx="12" cy="12" r="10"></circle>
          <line x1="12" y1="16" x2="12" y2="12"></line>
          <line x1="12" y1="8" x2="12.01" y2="8"></line>
        </svg>`,
                done: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2">
          <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
          <circle cx="12" cy="12" r="3"></circle>
        </svg>`,
                error: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2">
          <circle cx="12" cy="12" r="10"></circle>
          <line x1="15" y1="9" x2="9" y2="15"></line>
          <line x1="9" y1="9" x2="15" y2="15"></line>
        </svg>`
            },
            output: {
                running: `<svg class="icon-spin" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" stroke-width="2">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
          <polyline points="17 8 12 3 7 8"></polyline>
          <line x1="12" y1="3" x2="12" y2="15"></line>
        </svg>`,
                done: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" stroke-width="2">
          <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
          <polyline points="22 4 12 14.01 9 11.01"></polyline>
        </svg>`,
                error: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2">
          <circle cx="12" cy="12" r="10"></circle>
          <line x1="15" y1="9" x2="9" y2="15"></line>
          <line x1="9" y1="9" x2="15" y2="15"></line>
        </svg>`
            }
        };

        return icons[type]?.[status] || icons.thought.done;
    }

    function _escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function _scrollToBottom() {
        const body = document.getElementById('thought-chain-body');
        if (body) {
            body.scrollTop = body.scrollHeight;
        }
    }

    // ==================== 公共 API ====================

    return {
        init,
        addStep,
        updateStep,
        completeStep,
        errorStep,
        addToolCall,
        completeToolCall,
        addThought,
        addObservation,
        addOutput,
        clear,
        getStepCount,
        findStepByTitle
    };
})();

// 导出全局
window.ThoughtChain = ThoughtChain;
