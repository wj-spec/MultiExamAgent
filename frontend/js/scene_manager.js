/**
 * scene_manager.js — v3.0 场景管理器
 *
 * 职责：
 * 1. 渲染「场景切换横幅」（当 Chat Agent 检测到命题/审题意图时）
 * 2. 管理「审题试题输入面板」（review 场景下展示）
 * 3. 协调 TodoBoard 的显示/隐藏与当前场景
 * 4. 场景切换动画
 */

const SceneManager = (() => {
  'use strict';

  // ==================== 状态 ====================
  let _currentScene = 'chat';   // chat | proposition | review
  let _sessionId = null;
  let _sendWs = null;           // WebSocket 发送函数（由 app.js 注入）

  // DOM 引用
  let _bannerEl = null;
  let _reviewPanelEl = null;
  let _examTextarea = null;
  let _charCountEl = null;

  // ==================== 初始化 ====================

  function init(sessionId, sendWsFn) {
    _sessionId = sessionId;
    _sendWs = sendWsFn;

    _bannerEl      = document.getElementById('scene-switch-banner');
    _reviewPanelEl = document.getElementById('review-exam-input-panel');
    _examTextarea  = document.getElementById('review-exam-textarea');
    _charCountEl   = document.getElementById('review-char-count');

    if (!_bannerEl || !_reviewPanelEl) {
      console.warn('[SceneManager] DOM 元素不存在，动态创建...');
      _injectDom();
      _bannerEl      = document.getElementById('scene-switch-banner');
      _reviewPanelEl = document.getElementById('review-exam-input-panel');
      _examTextarea  = document.getElementById('review-exam-textarea');
      _charCountEl   = document.getElementById('review-char-count');
    }

    // 文件输入（可能不存在，初始化后绑定）
    const fileInput = document.getElementById('review-file-input');
    if (fileInput) fileInput.addEventListener('change', _handleFileUpload);

    _bindEvents();
    _restoreScene();
  }

  // ==================== DOM 注入 ====================

  function _injectDom() {
    // 场景切换横幅（注入到 #message-list 之前）
    const messageList = document.getElementById('message-list');
    if (messageList) {
      const banner = document.createElement('div');
      banner.id = 'scene-switch-banner';
      banner.innerHTML = `
        <div class="scene-banner-icon" id="scene-banner-icon">📝</div>
        <div class="scene-banner-text">
          <div class="scene-banner-title" id="scene-banner-title">切换到命题场景</div>
          <div class="scene-banner-desc" id="scene-banner-desc">AI Planner 将自动为您制定专业命题任务清单</div>
        </div>
        <div class="scene-banner-actions">
          <button class="scene-banner-btn primary" id="scene-banner-confirm">✓ 切换</button>
          <button class="scene-banner-btn secondary" id="scene-banner-dismiss">留在当前模式</button>
        </div>
      `;
      messageList.parentNode.insertBefore(banner, messageList);
    }

    // 审题输入面板（注入到 #input-area 内部，textarea 上方）
    const inputArea = document.getElementById('input-area');
    if (inputArea) {
      const panel = document.createElement('div');
      panel.id = 'review-exam-input-panel';
      panel.innerHTML = `
        <div class="review-input-header">
          <div class="review-input-label">
            <span>🔍</span> 审题输入
          </div>
          <div class="review-input-options">
            <label class="review-upload-btn" title="上传试卷文件">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48"></path>
              </svg>
              上传文件
              <input type="file" id="review-file-input"
                accept=".pdf,.doc,.docx,.txt,.md"
                style="display:none"
              />
            </label>
            <button class="review-toggle-btn" id="review-toggle-textarea" title="展开/收起文本输入">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                <polyline points="14 2 14 8 20 8"></polyline>
                <line x1="16" y1="13" x2="8" y2="13"></line>
                <line x1="16" y1="17" x2="8" y2="17"></line>
              </svg>
              粘贴文本
            </button>
          </div>
        </div>
        <div class="review-textarea-wrapper" id="review-textarea-wrapper" style="display: none;">
          <textarea
            id="review-exam-textarea"
            placeholder="将试题/试卷内容粘贴到这里...&#10;&#10;支持：纯文本题目、Markdown 格式、结构化题目列表"
            spellcheck="false"
          ></textarea>
          <div class="review-input-actions">
            <span class="review-char-count" id="review-char-count">0 字符</span>
          </div>
        </div>
      `;
      inputArea.insertBefore(panel, inputArea.firstChild);
    }
  }

  // ==================== 事件绑定 ====================

  function _bindEvents() {
    // 横幅：确认切换
    document.getElementById('scene-banner-confirm')?.addEventListener('click', () => {
      const targetScene = _bannerEl?.dataset.targetScene || 'proposition';
      switchScene(targetScene);
      hideBanner();
    });

    // 横幅：稍后再说
    document.getElementById('scene-banner-dismiss')?.addEventListener('click', () => {
      hideBanner();
    });

    // 字符计数
    _examTextarea?.addEventListener('input', () => {
      const count = _examTextarea.value.length;
      if (_charCountEl) _charCountEl.textContent = `${count.toLocaleString()} 字符`;
    });

    // 文件上传按钮（动态绑定，因为 _injectDom 后复查询）
    const fileInput = document.getElementById('review-file-input');
    fileInput?.addEventListener('change', _handleFileUpload);

    // 文本输入区域展开/收起按钮
    document.getElementById('review-toggle-textarea')?.addEventListener('click', () => {
      const wrapper = document.getElementById('review-textarea-wrapper');
      const btn = document.getElementById('review-toggle-textarea');
      if (wrapper) {
        const isVisible = wrapper.style.display !== 'none';
        wrapper.style.display = isVisible ? 'none' : 'block';
        btn?.classList.toggle('active', !isVisible);
      }
    });

    // 模式切换按钮由 ModeSwitch 模块统一处理，此处不再重复绑定
    // ModeSwitch.switchToMode() 会调用 SceneManager.switchScene()
  }

  // ==================== 场景切换 ====================

  /**
   * 切换到指定场景
   * @param {'chat'|'proposition'|'review'} scene
   */
  function switchScene(scene) {
    if (scene === _currentScene) return;

    const prevScene = _currentScene;
    _currentScene = scene;

    // 隐藏切换建议横幅（用户已主动切换）
    hideBanner();

    // 通知服务端（可选，由服务端维护场景状态）
    _sendWs?.({ type: 'switch_scene', scene });

    // 更新 UI
    _updateSceneUI(scene, prevScene);
    _saveScene(scene);

    console.log(`[SceneManager] 场景切换: ${prevScene} → ${scene}`);
  }

  function _updateSceneUI(scene, prevScene) {
    // 1. 切换 body class（驱动 CSS 主题）
    document.body.classList.remove('mode-chat', 'mode-proposition', 'mode-grading', 'scene-review', 'scene-proposition');
    if (scene === 'proposition') {
      document.body.classList.add('mode-proposition', 'scene-proposition');
    } else if (scene === 'review') {
      document.body.classList.add('mode-grading', 'scene-review');
    } else {
      document.body.classList.add('mode-chat');
    }

    // 2. 激活顶部 mode-btn
    const btnMap = { chat: 'btn-mode-chat', proposition: 'btn-mode-proposition', review: 'btn-mode-grading' };
    Object.entries(btnMap).forEach(([s, id]) => {
      document.getElementById(id)?.classList.toggle('active', s === scene);
    });

    // 3. 更新场景标签文字
    const currentModeEl = document.getElementById('current-mode');
    if (currentModeEl) {
      currentModeEl.textContent = { chat: '对话', proposition: '命题', review: '审题' }[scene] || scene;
    }

    // 4. 审题面板的显示
    if (scene === 'review') {
      _reviewPanelEl?.classList.add('visible');
      // input 区 placeholder 提示 - 允许直接输入审题需求
      const chatInput = document.getElementById('chat-input');
      if (chatInput) chatInput.placeholder = '输入审题需求或粘贴试题内容... (Enter 发送)';
    } else {
      _reviewPanelEl?.classList.remove('visible');
      const chatInput = document.getElementById('chat-input');
      if (chatInput) chatInput.placeholder = '输入您的需求... (Enter 发送，Shift+Enter 换行)';
    }

    // 5. 容器显隐切换 (v3.1 Split-Screen)
    const chatContainer = document.getElementById('chat-container');
    const workspaceContainer = document.getElementById('workspace-container');

    if (scene !== 'chat') {
      if (chatContainer) chatContainer.classList.add('hidden');
      if (workspaceContainer) workspaceContainer.classList.remove('hidden');

      if (typeof TodoBoard !== 'undefined') {
        TodoBoard.show();
      }
    } else {
      if (chatContainer) chatContainer.classList.remove('hidden');
      if (workspaceContainer) workspaceContainer.classList.add('hidden');

      if (typeof TodoBoard !== 'undefined') {
        TodoBoard.hide();
      }
    }

    // 6. 发送 WS 切换通知（让服务端知道当前场景）
    _sendWs?.({ type: 'switch_scene', scene });
  }

  // ==================== 场景切换横幅 ====================

  /**
   * 显示场景切换建议横幅
   * @param {'proposition'|'review'} targetScene  推荐场景
   */
  function showSwitchHint(targetScene) {
    if (!_bannerEl) return;
    if (_currentScene === targetScene) return;  // 已在目标场景，不需要提示

    const config = {
      proposition: {
        icon: '📝',
        title: '任务已完成，建议切换到命题模式',
        desc: '切换后可获得更专业的命题工作台、任务看板等功能',
      },
      review: {
        icon: '🔍',
        title: '任务已完成，建议切换到审题模式',
        desc: '切换后可获得更专业的审题工作台、批注视图等功能',
      },
    };

    const cfg = config[targetScene];
    if (!cfg) return;

    _bannerEl.dataset.targetScene = targetScene;

    const icon  = document.getElementById('scene-banner-icon');
    const title = document.getElementById('scene-banner-title');
    const desc  = document.getElementById('scene-banner-desc');
    if (icon)  icon.textContent  = cfg.icon;
    if (title) title.textContent = cfg.title;
    if (desc)  desc.textContent  = cfg.desc;

    // 重置动画
    _bannerEl.classList.remove('visible');
    void _bannerEl.offsetWidth;
    _bannerEl.classList.add('visible');

    // 15 秒后自动消失（给用户更多时间考虑）
    clearTimeout(SceneManager._bannerTimer);
    SceneManager._bannerTimer = setTimeout(() => hideBanner(), 15000);
  }

  function hideBanner() {
    _bannerEl?.classList.remove('visible');
    clearTimeout(SceneManager._bannerTimer);
  }

  // ==================== 审题提交 ====================

  /**
   * 处理审题场景的消息发送
   * 可从对话框直接输入，也可从粘贴区域输入
   * @param {string} chatInputContent - 对话框输入的内容
   * @returns {object|null} - 返回组合后的消息内容，或 null 表示不应处理
   */
  function buildReviewMessage(chatInputContent) {
    const examContent = _examTextarea?.value?.trim() || '';
    const userInstructions = chatInputContent?.trim() || '';

    // 如果有粘贴的试题内容，组合消息
    if (examContent) {
      const combined = `[待审试题]\n${examContent}\n\n${userInstructions || '请为以上试题制定专业审题计划。'}`;
      // 清空粘贴区域
      if (_examTextarea) _examTextarea.value = '';
      if (_charCountEl) _charCountEl.textContent = '0 字符';
      return { content: combined, scene: 'review' };
    }

    // 如果只有对话框输入，直接作为审题需求发送
    if (userInstructions) {
      return { content: userInstructions, scene: 'review' };
    }

    return null;
  }

  function _handleReviewSubmit() {
    const chatInput = document.getElementById('chat-input');
    const messageData = buildReviewMessage(chatInput?.value || '');

    if (!messageData) {
      // 尝试展开粘贴区域提示用户
      const wrapper = document.getElementById('review-textarea-wrapper');
      if (wrapper) wrapper.style.display = 'block';
      chatInput?.focus();
      return;
    }

    // 通过全局事件让 app.js 发送消息
    window.dispatchEvent(new CustomEvent('scene:send-message', {
      detail: messageData
    }));

    // 清空对话框输入
    if (chatInput) chatInput.value = '';
  }

  // ==================== 文件上传 ====================

  async function _handleFileUpload(event) {
    const file = event.target.files?.[0];
    if (!file) return;

    const labelEl = document.querySelector('label[title="上传试卷文件"]');
    const originalText = labelEl?.querySelector('span')?.textContent;

    // 显示加载状态
    if (labelEl) labelEl.style.opacity = '0.6';
    if (_examTextarea) {
      _examTextarea.placeholder = `⏳ 正在解析 ${file.name}...`;
    }

    try {
      const formData = new FormData();
      formData.append('file', file);

      const resp = await fetch('/api/todos/review/upload-exam', {
        method: 'POST',
        body: formData,
      });

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: resp.statusText }));
        throw new Error(err.detail || '上传失败');
      }

      const data = await resp.json();

      // 填充到 textarea 并展开显示
      if (_examTextarea) {
        const prev = _examTextarea.value.trim();
        _examTextarea.value = prev ? `${prev}\n\n---\n\n${data.content}` : data.content;
        _examTextarea.dispatchEvent(new Event('input'));  // 触发字数统计
        _examTextarea.scrollTop = 0;
        // 展开显示 textarea
        const wrapper = document.getElementById('review-textarea-wrapper');
        if (wrapper) wrapper.style.display = 'block';
      }

      // 简短提示
      if (labelEl) {
        labelEl.style.opacity = '';
        const info = `✅ 已提取 ${(data.char_count || 0).toLocaleString()} 字符`;
        const span = labelEl.querySelector('span');
        if (span) { span.textContent = info; setTimeout(() => { span.textContent = originalText || '📄'; }, 3000); }
      }

    } catch (err) {
      console.error('[SceneManager] 文件上传失败:', err);
      if (labelEl) labelEl.style.opacity = '';
      if (_examTextarea) {
        _examTextarea.placeholder = `❌ 文件解析失败: ${err.message}，请直接粘贴文本`;
        setTimeout(() => {
          _examTextarea.placeholder = '将试题/试卷内容粘贴到这里...';
        }, 4000);
      }
    } finally {
      // 重置 file input（允许再次选同一文件）
      event.target.value = '';
    }
  }

  // ==================== 持久化 ====================

  function _saveScene(scene) {
    try { localStorage.setItem('intelliexam_scene', scene); } catch {}
  }

  function _restoreScene() {
    try {
      const saved = localStorage.getItem('intelliexam_scene');
      if (saved && saved !== 'chat') {
        switchScene(saved);
      }
    } catch {}
  }

  // ==================== 公共 API ====================

  function getCurrentScene() { return _currentScene; }

  return {
    init,
    switchScene,
    showSwitchHint,
    hideBanner,
    getCurrentScene,
    buildReviewMessage,  // 供 app.js 在审题场景下构建消息
    _bannerTimer: null,
  };
})();
