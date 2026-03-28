/**
 * outline_confirm.js
 * 
 * Human-in-the-loop 大纲确认交互组件
 * 
 * 设计文档要求：
 * - 大规模生成题目前，Agent先产出"组卷大纲/双向细目表"
 * - 暂停等待用户"确认生成"或"调整大纲"
 * - 避免长时任务跑错方向
 * 
 * 核心功能：
 * 1. 展示命题大纲/双向细目表
 * 2. 用户确认/修改大纲
 * 3. 支持用户反馈输入
 * 4. 与 WebSocket 通信
 */

const OutlineConfirm = (() => {
    'use strict';

    // ==================== 状态 ====================
    let _containerEl = null;
    let _currentOutline = null;
    let _onConfirm = null;
    let _onModify = null;
    let _sendWs = null;

    // ==================== 初始化 ====================

    /**
     * 初始化大纲确认组件
     * @param {Object} options - 配置选项
     * @param {Function} options.onConfirm - 确认回调
     * @param {Function} options.onModify - 修改回调
     * @param {Function} options.sendWs - WebSocket 发送函数
     */
    function init(options = {}) {
        _onConfirm = options.onConfirm;
        _onModify = options.onModify;
        _sendWs = options.sendWs;
    }

    // ==================== 核心方法 ====================

    /**
     * 显示大纲确认卡片
     * @param {Object} outline - 大纲数据
     * @param {string} containerId - 容器ID
     */
    function show(outline, containerId = 'workspace-canvas-content') {
        _containerEl = document.getElementById(containerId);
        if (!_containerEl) {
            console.warn('[OutlineConfirm] 容器元素不存在:', containerId);
            return;
        }

        _currentOutline = outline;

        const html = _renderOutlineCard(outline);
        _containerEl.innerHTML = html;

        _bindEvents();
    }

    /**
     * 隐藏大纲确认卡片
     */
    function hide() {
        if (_containerEl) {
            _containerEl.innerHTML = `
        <div class="empty-canvas-state">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="opacity: 0.3; margin-bottom: 12px;">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
            <polyline points="14 2 14 8 20 8"></polyline>
            <line x1="16" y1="13" x2="8" y2="13"></line>
            <line x1="16" y1="17" x2="8" y2="17"></line>
          </svg>
          <p>正在生成命题内容...</p>
        </div>
      `;
        }
        _currentOutline = null;
    }

    /**
     * 获取当前大纲
     */
    function getCurrentOutline() {
        return _currentOutline;
    }

    /**
     * 更新大纲数据
     * @param {Object} updates - 更新内容
     */
    function updateOutline(updates) {
        if (_currentOutline) {
            _currentOutline = { ..._currentOutline, ...updates };
        }
    }

    // ==================== 渲染方法 ====================

    function _renderOutlineCard(outline) {
        const {
            title = '命题大纲',
            description = '',
            examSpec = {},
            questionDistribution = [],
            difficultyDistribution = {},
            estimatedTime = ''
        } = outline;

        return `
      <div class="outline-confirm-card" id="outline-confirm-card">
        <div class="outline-confirm-header">
          <div class="outline-confirm-icon">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#a78bfa" stroke-width="2">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
              <polyline points="14 2 14 8 20 8"></polyline>
              <line x1="16" y1="13" x2="8" y2="13"></line>
              <line x1="16" y1="17" x2="8" y2="17"></line>
            </svg>
          </div>
          <div>
            <div class="outline-confirm-title">${title}</div>
            <div class="outline-confirm-desc">${description || '请确认以下命题大纲，确认后将开始生成试题'}</div>
          </div>
        </div>

        <!-- 试卷规格 -->
        ${_renderExamSpec(examSpec)}

        <!-- 题型分布 -->
        ${_renderQuestionDistribution(questionDistribution)}

        <!-- 难度分布 -->
        ${_renderDifficultyDistribution(difficultyDistribution)}

        <!-- 预计时间 -->
        ${estimatedTime ? `
          <div class="outline-section">
            <div class="outline-section-title">⏱️ 预计生成时间</div>
            <div class="outline-time-estimate">${estimatedTime}</div>
          </div>
        ` : ''}

        <!-- 操作按钮 -->
        <div class="outline-actions">
          <button class="outline-btn outline-btn-primary" id="outline-confirm-btn">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="20 6 9 17 4 12"></polyline>
            </svg>
            确认生成
          </button>
          <button class="outline-btn outline-btn-secondary" id="outline-modify-btn">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
              <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
            </svg>
            调整大纲
          </button>
        </div>

        <!-- 修改反馈区（默认隐藏） -->
        <div class="outline-feedback" id="outline-feedback" style="display: none;">
          <textarea id="outline-feedback-input" placeholder="请描述您希望如何调整大纲，例如：&#10;- 增加选择题数量到10道&#10;- 降低整体难度&#10;- 增加函数知识点的题目"></textarea>
          <div class="outline-feedback-actions">
            <button class="outline-btn outline-btn-secondary" id="outline-cancel-btn">取消</button>
            <button class="outline-btn outline-btn-primary" id="outline-submit-btn">提交修改</button>
          </div>
        </div>
      </div>
    `;
    }

    function _renderExamSpec(spec) {
        if (!spec || Object.keys(spec).length === 0) return '';

        const {
            subject = '',
            grade = '',
            totalQuestions = 0,
            totalScore = 100,
            duration = ''
        } = spec;

        return `
      <div class="outline-section">
        <div class="outline-section-title">📋 试卷规格</div>
        <div class="outline-spec-grid">
          ${subject ? `<div class="spec-item"><span class="spec-label">学科</span><span class="spec-value">${subject}</span></div>` : ''}
          ${grade ? `<div class="spec-item"><span class="spec-label">年级</span><span class="spec-value">${grade}</span></div>` : ''}
          ${totalQuestions ? `<div class="spec-item"><span class="spec-label">题目数量</span><span class="spec-value">${totalQuestions} 题</span></div>` : ''}
          ${totalScore ? `<div class="spec-item"><span class="spec-label">总分</span><span class="spec-value">${totalScore} 分</span></div>` : ''}
          ${duration ? `<div class="spec-item"><span class="spec-label">考试时长</span><span class="spec-value">${duration}</span></div>` : ''}
        </div>
      </div>
    `;
    }

    function _renderQuestionDistribution(distribution) {
        if (!distribution || distribution.length === 0) return '';

        return `
      <div class="outline-section">
        <div class="outline-section-title">📊 题型分布</div>
        <div class="outline-distribution">
          ${distribution.map(item => `
            <div class="distribution-item">
              <div class="distribution-header">
                <span class="distribution-type">${item.type || '未知题型'}</span>
                <span class="distribution-count">${item.count || 0} 题</span>
              </div>
              <div class="distribution-bar">
                <div class="distribution-bar-fill" style="width: ${item.percentage || 0}%"></div>
              </div>
              ${item.topics && item.topics.length > 0 ? `
                <div class="distribution-topics">
                  知识点: ${item.topics.join('、')}
                </div>
              ` : ''}
            </div>
          `).join('')}
        </div>
      </div>
    `;
    }

    function _renderDifficultyDistribution(distribution) {
        if (!distribution || Object.keys(distribution).length === 0) return '';

        const { easy = 0, medium = 0, hard = 0 } = distribution;
        const total = easy + medium + hard;

        return `
      <div class="outline-section">
        <div class="outline-section-title">📈 难度分布</div>
        <div class="difficulty-distribution">
          <div class="difficulty-item difficulty-easy">
            <span class="difficulty-label">简单</span>
            <div class="difficulty-bar">
              <div class="difficulty-bar-fill" style="width: ${total ? (easy / total * 100) : 0}%"></div>
            </div>
            <span class="difficulty-count">${easy}</span>
          </div>
          <div class="difficulty-item difficulty-medium">
            <span class="difficulty-label">中等</span>
            <div class="difficulty-bar">
              <div class="difficulty-bar-fill" style="width: ${total ? (medium / total * 100) : 0}%"></div>
            </div>
            <span class="difficulty-count">${medium}</span>
          </div>
          <div class="difficulty-item difficulty-hard">
            <span class="difficulty-label">困难</span>
            <div class="difficulty-bar">
              <div class="difficulty-bar-fill" style="width: ${total ? (hard / total * 100) : 0}%"></div>
            </div>
            <span class="difficulty-count">${hard}</span>
          </div>
        </div>
      </div>
    `;
    }

    // ==================== 事件处理 ====================

    function _bindEvents() {
        // 确认按钮
        document.getElementById('outline-confirm-btn')?.addEventListener('click', _handleConfirm);

        // 修改按钮
        document.getElementById('outline-modify-btn')?.addEventListener('click', _handleShowFeedback);

        // 取消修改
        document.getElementById('outline-cancel-btn')?.addEventListener('click', _handleCancelFeedback);

        // 提交修改
        document.getElementById('outline-submit-btn')?.addEventListener('click', _handleSubmitFeedback);
    }

    function _handleConfirm() {
        // 发送确认消息到服务端
        if (_sendWs) {
            _sendWs({
                type: 'outline_confirm',
                outline: _currentOutline
            });
        }

        // 调用回调
        if (_onConfirm) {
            _onConfirm(_currentOutline);
        }

        // 显示确认状态
        const card = document.getElementById('outline-confirm-card');
        if (card) {
            card.innerHTML = `
        <div style="text-align: center; padding: 40px;">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2" style="margin-bottom: 16px;">
            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
            <polyline points="22 4 12 14.01 9 11.01"></polyline>
          </svg>
          <div style="font-size: 16px; font-weight: 600; color: #6ee7b7; margin-bottom: 8px;">大纲已确认</div>
          <div style="font-size: 13px; color: var(--text-muted);">正在开始生成试题...</div>
        </div>
      `;
        }
    }

    function _handleShowFeedback() {
        const feedbackEl = document.getElementById('outline-feedback');
        if (feedbackEl) {
            feedbackEl.style.display = 'block';
            document.getElementById('outline-feedback-input')?.focus();
        }
    }

    function _handleCancelFeedback() {
        const feedbackEl = document.getElementById('outline-feedback');
        if (feedbackEl) {
            feedbackEl.style.display = 'none';
        }
    }

    function _handleSubmitFeedback() {
        const input = document.getElementById('outline-feedback-input');
        const feedback = input?.value?.trim();

        if (!feedback) {
            input?.focus();
            return;
        }

        // 发送修改请求到服务端
        if (_sendWs) {
            _sendWs({
                type: 'outline_modify',
                outline: _currentOutline,
                feedback: feedback
            });
        }

        // 调用回调
        if (_onModify) {
            _onModify(_currentOutline, feedback);
        }

        // 显示修改状态
        const card = document.getElementById('outline-confirm-card');
        if (card) {
            card.innerHTML = `
        <div style="text-align: center; padding: 40px;">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#a78bfa" stroke-width="2" style="margin-bottom: 16px; animation: iconSpin 1s linear infinite;">
            <path d="M21 12a9 9 0 1 1-6.219-8.56"></path>
          </svg>
          <div style="font-size: 16px; font-weight: 600; color: var(--brand-light); margin-bottom: 8px;">正在重新规划...</div>
          <div style="font-size: 13px; color: var(--text-muted);">根据您的反馈调整大纲中</div>
        </div>
      `;
        }
    }

    // ==================== 公共 API ====================

    return {
        init,
        show,
        hide,
        getCurrentOutline,
        updateOutline
    };
})();

// 导出全局
window.OutlineConfirm = OutlineConfirm;
