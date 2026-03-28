/**
 * todo_board.js - 待办任务看板交互逻辑
 *
 * 职责：
 * - 渲染 TodoGroup 和 TodoTask 卡片
 * - 处理评论添加、任务状态更新
 * - 响应 WebSocket 推送的 todo_* 事件
 * - 暴露 TodoBoard 全局对象供 app.js 调用
 */

const TodoBoard = (() => {
  'use strict';

  // ==================== 状态 ====================
  let _currentGroup = null;       // 当前任务组
  let _sessionId = null;          // 当前会话 ID
  let _panelEl = null;            // 面板根元素
  let _taskListEl = null;         // 任务列表容器
  let _summaryEl = null;          // Planner 规划说明
  let _doneBannerEl = null;       // 全部完成横幅

  // ==================== 初始化 ====================

  function init(sessionId) {
    _sessionId = sessionId;
    _panelEl = document.getElementById('todo-board-panel');
    if (!_panelEl) {
      console.warn('[TodoBoard] 面板元素不存在，动态创建...');
      _createPanel();
    }
    _taskListEl = _panelEl.querySelector('.todo-task-list');
    _summaryEl = _panelEl.querySelector('.todo-planner-summary-text');
    _doneBannerEl = _panelEl.querySelector('.todo-board-done-banner');
  }

  // ==================== DOM 构建 ====================

  function _createPanel() {
    _panelEl = document.createElement('div');
    _panelEl.id = 'todo-board-panel';
    _panelEl.innerHTML = `
      <div class="todo-board-header">
        <div class="todo-board-title">
          <div class="todo-board-title-icon">✓</div>
          <span id="todo-board-group-title">任务规划</span>
          <span class="todo-board-scene-badge" id="todo-board-scene-badge">命题</span>
        </div>
        <div class="todo-board-actions">
          <button class="todo-board-btn primary" id="todo-confirm-btn" title="确认执行所有任务">
            ▶ 开始执行
          </button>
        </div>
      </div>

      <div class="todo-board-done-banner" id="todo-done-banner">
        ✅ 所有任务已完成
      </div>

      <div class="todo-planner-summary" id="todo-planner-summary" style="display:none">
        <div class="todo-planner-summary-label">🤖 规划说明</div>
        <div class="todo-planner-summary-text"></div>
      </div>

      <div class="todo-task-list" id="todo-task-list">
        <div class="todo-board-empty">
          <div class="todo-board-empty-icon">📋</div>
          <div class="todo-board-empty-title">等待 AI 规划...</div>
          <div class="todo-board-empty-desc">发送命题或审题需求，Planner 将自动生成任务清单</div>
        </div>
      </div>
    `;

    // 插入到主布局的 #chat-main 之后
    const chatMain = document.getElementById('chat-main');
    if (chatMain && chatMain.parentNode) {
      chatMain.parentNode.insertBefore(_panelEl, chatMain.nextSibling);
    } else {
      document.getElementById('app')?.appendChild(_panelEl);
    }

    // 重新查询子元素
    _taskListEl = _panelEl.querySelector('.todo-task-list');
    _summaryEl = _panelEl.querySelector('.todo-planner-summary-text');
    _doneBannerEl = _panelEl.querySelector('.todo-board-done-banner');

    // 绑定"开始执行"按钮
    _panelEl.querySelector('#todo-confirm-btn')?.addEventListener('click', _handleConfirmAll);
  }

  // ==================== 公共 API ====================

  /** 显示/隐藏看板面板 */
  function show() {
    _panelEl?.classList.add('visible');
    // 主对话区宽度收窄
    const chatMain = document.getElementById('chat-main');
    if (chatMain) chatMain.style.minWidth = '340px';
  }

  function hide() {
    _panelEl?.classList.remove('visible');
    const chatMain = document.getElementById('chat-main');
    if (chatMain) chatMain.style.minWidth = '';
    _currentGroup = null;
  }

  /**
   * 渲染整个任务组（从 WebSocket todo_group_created 事件调用）
   * @param {object} group - TodoGroup 数据
   */
  function renderGroup(group) {
    _currentGroup = group;
    show();

    // 更新标题和场景 badge
    const titleEl = _panelEl.querySelector('#todo-board-group-title');
    if (titleEl) titleEl.textContent = group.title || '任务规划';

    const badgeEl = _panelEl.querySelector('#todo-board-scene-badge');
    if (badgeEl) {
      badgeEl.textContent = group.scene === 'review' ? '审题' : '命题';
      badgeEl.className = `todo-board-scene-badge${group.scene === 'review' ? ' review' : ''}`;
    }

    // 显示规划说明
    if (group.planner_summary && _summaryEl) {
      _summaryEl.textContent = group.planner_summary;
      _panelEl.querySelector('#todo-planner-summary').style.display = 'block';
    }

    // 渲染任务列表
    if (_taskListEl) {
      _taskListEl.innerHTML = '';
      const sorted = [...(group.tasks || [])].sort((a, b) => a.order - b.order);
      sorted.forEach(task => {
        _taskListEl.appendChild(_buildTaskCard(task));
      });
    }

    _updateDoneBanner();
  }

  /**
   * 更新单个任务状态（从 WebSocket todo_task_update 调用）
   * @param {object} task - 更新后的 TodoTask
   */
  function updateTask(task) {
    if (!_currentGroup) return;

    // 更新内存中的任务
    const idx = _currentGroup.tasks.findIndex(t => t.id === task.id);
    if (idx !== -1) {
      _currentGroup.tasks[idx] = { ..._currentGroup.tasks[idx], ...task };
    }

    // 更新 DOM 中的卡片
    const card = _taskListEl?.querySelector(`[data-task-id="${task.id}"]`);
    if (card) {
      _updateCardStatus(card, task);
    }

    _updateDoneBanner();
  }

  /**
   * 任务执行完成，展示结果（从 WebSocket todo_task_result 调用）
   */
  function showTaskResult(taskId, result, elapsedMs) {
    const card = _taskListEl?.querySelector(`[data-task-id="${taskId}"]`);
    if (!card) return;

    // 更新任务的 result
    if (_currentGroup) {
      const t = _currentGroup.tasks.find(t => t.id === taskId);
      if (t) t.result = result;
    }

    // 展示结果区域
    let resultEl = card.querySelector('.todo-card-result');
    if (resultEl) {
      resultEl.innerHTML = `<div class="todo-card-result-markdown">${_renderMd(result)}</div>`;
      resultEl.classList.add('expanded');
    }

    // 更新耗时
    if (elapsedMs) {
      const elapsedEl = card.querySelector('.todo-card-elapsed-val');
      if (elapsedEl) elapsedEl.textContent = `${(elapsedMs / 1000).toFixed(1)}s`;
    }
  }

  /**
   * 添加新评论到指定任务卡片（从 WebSocket todo_comment_added 调用）
   */
  function addComment(taskId, comment) {
    const card = _taskListEl?.querySelector(`[data-task-id="${taskId}"]`);
    if (!card) return;

    const commentsList = card.querySelector('.todo-comments-list');
    if (commentsList) {
      commentsList.appendChild(_buildCommentItem(comment));
      // 更新评论计数
      const countEl = card.querySelector('.todo-comments-count');
      if (countEl) countEl.textContent = parseInt(countEl.textContent || '0') + 1;
      // 自动展开
      _openComments(card);
    }
  }

  // ==================== 卡片构建 ====================

  function _buildTaskCard(task) {
    const card = document.createElement('div');
    card.className = 'todo-card';
    card.dataset.taskId = task.id;
    card.dataset.status = task.status;

    const statusInfo = _getStatusInfo(task.status);
    const comments = task.comments || [];
    const hasResult = task.result && task.status === 'done';

    card.innerHTML = `
      <div class="todo-card-strip"></div>
      <div class="todo-card-body">
        <div class="todo-card-top">
          <div class="todo-card-title">${_esc(task.title)}</div>
          <span class="todo-status-badge ${task.status}">${statusInfo.icon} ${statusInfo.label}</span>
        </div>
        ${task.description ? `<div class="todo-card-desc">${_esc(task.description)}</div>` : ''}
        ${task.status === 'running' ? `
          <div class="todo-card-progress">
            <div class="todo-task-active-step" style="font-size:11.5px; color:#4b5563; margin-bottom:4px; font-weight:500;">
              ${task.current_step ? '🤖 '+_esc(task.current_step) : '正在执行...'}
            </div>
            <div class="todo-card-progress-bar" style="width: 100%; animation: slide 1.5s infinite"></div>
          </div>` : ''}
        <div class="todo-card-meta">
          <span class="task-type-label">${_getTaskTypeLabel(task.task_type)}</span>
          <span class="todo-card-elapsed">
            ${task.elapsed_ms ? `⏱ <span class="todo-card-elapsed-val">${(task.elapsed_ms / 1000).toFixed(1)}s</span>` : ''}
          </span>
        </div>
        ${_buildActionButtons(task)}
        <div class="todo-card-result${hasResult ? ' expanded' : ''}">
          ${hasResult ? `<div class="todo-card-result-markdown">${_renderMd(task.result)}</div>` : ''}
        </div>
      </div>
      <div class="todo-card-comments">
        <div class="todo-comments-toggle" data-task-id="${task.id}">
          <span class="chevron">▶</span>
          <span>评论</span>
          <span class="todo-comments-count">${comments.length}</span>
        </div>
        <div class="todo-comments-list">
          ${comments.map(c => _buildCommentItem(c).outerHTML).join('')}
        </div>
        <div class="todo-comment-input-area">
          <textarea class="todo-comment-input" placeholder="添加备注或修改意见..." rows="1"></textarea>
          <button class="todo-comment-submit" data-task-id="${task.id}" title="提交评论">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>
            </svg>
          </button>
        </div>
      </div>
    `;

    // 绑定事件
    _bindCardEvents(card, task);
    return card;
  }

  function _buildActionButtons(task) {
    const btns = [];
    if (task.status === 'ready' || task.status === 'need_revision') {
      btns.push(`<button class="todo-card-action-btn run-btn" data-action="run" data-task-id="${task.id}">▶ 立即执行</button>`);
    }
    if (task.status === 'done' && task.result) {
      btns.push(`<button class="todo-card-action-btn view-btn" data-action="toggle-result" data-task-id="${task.id}">📄 查看结果</button>`);
    }
    btns.push(`<button class="todo-card-action-btn" data-action="add-comment" data-task-id="${task.id}">💬 评论</button>`);
    return `<div class="todo-card-actions">${btns.join('')}</div>`;
  }

  function _buildCommentItem(comment) {
    const el = document.createElement('div');
    el.className = 'todo-comment-item';
    const isAgent = comment.author === 'agent';
    const time = _formatTime(comment.created_at);
    el.innerHTML = `
      <div class="todo-comment-avatar ${isAgent ? 'agent' : 'user'}">${isAgent ? '🤖' : '👤'}</div>
      <div class="todo-comment-bubble ${isAgent ? 'agent' : ''}">
        <div class="todo-comment-meta">
          <span class="todo-comment-author">${isAgent ? 'AI 助手' : '我'}</span>
          <span class="todo-comment-time">${time}</span>
        </div>
        <div class="todo-comment-content">${_esc(comment.content)}</div>
      </div>
    `;
    return el;
  }

  // ==================== 卡片状态更新 ====================

  function _updateCardStatus(card, task) {
    card.dataset.status = task.status;

    // 更新 badge
    const badge = card.querySelector('.todo-status-badge');
    if (badge) {
      const info = _getStatusInfo(task.status);
      badge.className = `todo-status-badge ${task.status}`;
      badge.textContent = `${info.icon} ${info.label}`;
    }

    // 显示/隐藏或更新进度条与 Agent 步骤
    const existing = card.querySelector('.todo-card-progress');
    if (task.status === 'running') {
      const stepText = task.current_step ? '🤖 ' + _esc(task.current_step) : '正在执行...';
      if (!existing) {
        const descEl = card.querySelector('.todo-card-desc');
        const progressHtml = `<div class="todo-card-progress">
            <div class="todo-task-active-step" style="font-size:11.5px; color:#4b5563; margin-bottom:4px; font-weight:500;">${stepText}</div>
            <div class="todo-card-progress-bar" style="width:100%; animation: fade 1.5s alternate infinite"></div>
          </div>`;
        if (descEl) { descEl.insertAdjacentHTML('afterend', progressHtml); }
        else { card.querySelector('.todo-card-top').insertAdjacentHTML('afterend', progressHtml); }
      } else {
        const stepEl = existing.querySelector('.todo-task-active-step');
        if (stepEl) stepEl.textContent = stepText;
      }
    } else if (task.status !== 'running' && existing) {
      existing.remove();
    }

    // 更新操作按钮
    const actionsEl = card.querySelector('.todo-card-actions');
    if (actionsEl) actionsEl.outerHTML = _buildActionButtons(task);
    _bindCardEvents(card, task);

    // 更新耗时
    if (task.elapsed_ms) {
      const elapsedEl = card.querySelector('.todo-card-elapsed');
      if (elapsedEl) elapsedEl.innerHTML = `⏱ <span class="todo-card-elapsed-val">${(task.elapsed_ms / 1000).toFixed(1)}s</span>`;
    }
  }

  // ==================== 事件绑定 ====================

  function _bindCardEvents(card, task) {
    // 评论展开/收起
    card.querySelector('.todo-comments-toggle')?.addEventListener('click', () => _toggleComments(card));

    // 动态按钮事件（使用事件委托）
    card.querySelector('.todo-card-actions')?.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-action]');
      if (!btn) return;
      const action = btn.dataset.action;
      const taskId = btn.dataset.taskId;

      if (action === 'toggle-result') {
        const resultEl = card.querySelector('.todo-card-result');
        resultEl?.classList.toggle('expanded');
      }
      if (action === 'add-comment') {
        _openCommentInput(card);
      }
      if (action === 'run') {
        _handleRunTask(taskId, card);
      }
    });

    // 提交评论按钮
    const submitBtn = card.querySelector('.todo-comment-submit');
    const inputEl = card.querySelector('.todo-comment-input');
    submitBtn?.addEventListener('click', () => _submitComment(task.id, card));
    inputEl?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        _submitComment(task.id, card);
      }
    });
    // 自动调整高度
    inputEl?.addEventListener('input', () => {
      inputEl.style.height = 'auto';
      inputEl.style.height = Math.min(inputEl.scrollHeight, 100) + 'px';
    });
  }

  function _toggleComments(card) {
    const toggle = card.querySelector('.todo-comments-toggle');
    const list = card.querySelector('.todo-comments-list');
    const inputArea = card.querySelector('.todo-comment-input-area');
    const isOpen = toggle.classList.contains('open');

    if (isOpen) {
      toggle.classList.remove('open');
      list.classList.remove('open');
      inputArea?.classList.remove('open');
    } else {
      _openComments(card);
    }
  }

  function _openComments(card) {
    card.querySelector('.todo-comments-toggle')?.classList.add('open');
    card.querySelector('.todo-comments-list')?.classList.add('open');
  }

  function _openCommentInput(card) {
    _openComments(card);
    const inputArea = card.querySelector('.todo-comment-input-area');
    inputArea?.classList.add('open');
    card.querySelector('.todo-comment-input')?.focus();
  }

  // ==================== 用户操作处理 ====================

  async function _submitComment(taskId, card) {
    const inputEl = card.querySelector('.todo-comment-input');
    const content = inputEl?.value?.trim();
    if (!content) return;

    inputEl.value = '';
    inputEl.style.height = 'auto';

    try {
      const res = await fetch(`/api/todos/tasks/${taskId}/comment`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content, author: 'user' })
      });
      if (!res.ok) throw new Error('提交失败');
      const comment = await res.json();

      // 本地渲染
      const commentsList = card.querySelector('.todo-comments-list');
      if (commentsList) {
        commentsList.appendChild(_buildCommentItem(comment));
        const countEl = card.querySelector('.todo-comments-count');
        if (countEl) countEl.textContent = parseInt(countEl.textContent || '0') + 1;
      }
    } catch (err) {
      console.error('[TodoBoard] 评论提交失败:', err);
    }
  }

  async function _handleConfirmAll() {
    if (!_currentGroup) return;
    const btn = _panelEl.querySelector('#todo-confirm-btn');
    if (btn) { btn.disabled = true; btn.textContent = '执行中...'; }

    try {
      // 触发 app.js 的 WS 发送
      window.dispatchEvent(new CustomEvent('todo:run-group', { detail: { groupId: _currentGroup.id } }));
      
      // 更新所有 pending 任务状态为 ready
      _currentGroup.tasks.forEach(t => {
        if (t.status === 'pending') {
          t.status = 'ready';
          const card = _taskListEl?.querySelector(`[data-task-id="${t.id}"]`);
          if (card) _updateCardStatus(card, t);
        }
      });
    } catch (err) {
      console.error('[TodoBoard] 确认执行失败:', err);
      if (btn) { btn.disabled = false; btn.textContent = '▶ 开始执行'; }
    }
  }

  function _handleRunTask(taskId, card) {
    // 通过 WebSocket 发送单任务执行请求（由外部 app.js 代理）
    const t = _currentGroup?.tasks.find(t => t.id === taskId);
    if (t) {
      t.status = 'running';
      _updateCardStatus(card, t);
    }
    // 触发全局事件，由 app.js 监听并发送 WS 消息
    window.dispatchEvent(new CustomEvent('todo:run-task', { detail: { taskId, groupId: _currentGroup?.id } }));
  }

  // ==================== 全部完成处理 ====================

  function _updateDoneBanner() {
    if (!_currentGroup || !_doneBannerEl) return;
    const tasks = _currentGroup.tasks || [];
    const runnable = tasks.filter(t => t.status !== 'skipped');
    const allDone = runnable.length > 0 && runnable.every(t => t.status === 'done');
    _doneBannerEl.classList.toggle('visible', allDone);

    // 更新"开始执行"按钮
    const btn = _panelEl.querySelector('#todo-confirm-btn');
    if (btn && allDone) {
      btn.textContent = '✅ 已完成';
      btn.disabled = true;
    }
  }

  // ==================== 工具函数 ====================

  function _getStatusInfo(status) {
    const map = {
      pending: { icon: '⚪', label: '待规划' },
      ready: { icon: '🔵', label: '待执行' },
      running: { icon: '🟡', label: '进行中' },
      done: { icon: '✅', label: '已完成' },
      need_revision: { icon: '⚠️', label: '需修订' },
      skipped: { icon: '⏭️', label: '已跳过' },
    };
    return map[status] || { icon: '⚪', label: status };
  }

  function _getTaskTypeLabel(type) {
    const map = {
      knowledge_analysis: '📚 知识点分析',
      question_generate: '✍️ 题目生成',
      difficulty_calibration: '📊 难度校准',
      quality_audit: '🔍 质量审核',
      answer_verify: '✔️ 答案验证',
      report_generate: '📋 报告生成',
      document_export: '📄 文档导出',
      comprehension: '📖 阅题梳理',
      syllabus_check: '📌 课标核查',
      science_check: '⚗️ 科学性审核',
      difficulty_assessment: '📈 难度评估',
      language_review: '📝 表述审核',
      scoring_review: '🏷️ 评分标准审核',
      general: '⚙️ 执行任务',
    };
    return map[type] || type || '';
  }

  function _renderMd(text) {
    try {
      if (!text) return '';
      // 允许保留 ins 和 del 标签以支持 diff 视图
      let html = typeof marked !== 'undefined'
        ? marked.parse(text)
        : _esc(text);
        
      if (typeof DOMPurify !== 'undefined') {
          html = DOMPurify.sanitize(html, { ADD_TAGS: ['ins', 'del'] });
      }
      return html;
    } catch { return _esc(text || ''); }
  }

  function _esc(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function _formatTime(isoStr) {
    if (!isoStr) return '';
    try {
      const d = new Date(isoStr);
      const now = new Date();
      const diff = (now - d) / 1000;
      if (diff < 60) return '刚刚';
      if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`;
      if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`;
      return d.toLocaleDateString();
    } catch { return ''; }
  }

  // ==================== 监听画布事件 ====================
  window.addEventListener('todo:local-rewrite', (e) => {
    const { taskId, selection, instruction } = e.detail;
    const card = _taskListEl?.querySelector(`[data-task-id="${taskId}"]`);
    if (card && _currentGroup) {
      const t = _currentGroup.tasks.find(t => t.id === taskId);
      if (t) {
        // 模拟执行状态更新
        t.status = 'running';
        _updateCardStatus(card, t);
        
        // 模拟后端返回 diff 请求
        setTimeout(() => {
          const simulatedDiffResult = (t.result || '').replace(selection, `<del>${selection}</del> <ins>[Agent根据你的指示：${instruction} 重写了这段文本]</ins>`);
          t.status = 'done';
          showTaskResult(taskId, simulatedDiffResult, 1500);
          _updateCardStatus(card, t);
        }, 1500);
      }
    }
  });

  // ==================== 暴露公共 API ====================

  return { init, show, hide, renderGroup, updateTask, showTaskResult, addComment };
})();
