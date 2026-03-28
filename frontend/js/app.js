/**
 * app.js - 应用主入口 & WebSocket 管理
 * 职责：初始化各模块、管理 WebSocket 连接、心跳保活、消息路由分发
 */

(function () {
  'use strict';

  // ==================== 配置 ====================
  const WS_RECONNECT_DELAY = 3000;
  const HEARTBEAT_INTERVAL = 25000;

  // ==================== 状态 ====================
  let ws = null;
  let sessionId = generateId();
  let heartbeatTimer = null;
  let reconnectTimer = null;
  let isHandlingTask = false;  // 是否正在处理 Agent 任务
  let lastResult = null;       // 缓存最后一次任务结果（用于查看结果按钮）
  let speculativeIndicatorEl = null;
  let pendingSceneSwitchHint = null;  // 待显示的场景切换建议（结果输出完毕后显示）
  let documentVersions = [];   // 文档历史版本记录
  let currentVersionIndex = -1; // 当前版本索引

  // ==================== 初始化 ====================

  document.addEventListener('DOMContentLoaded', () => {
    // 初始化各模块
    Panel.init();
    Sidebar.init(handleSwitchConversation);
    Chat.init(handleSendMessage, handleShowResult);
    
    speculativeIndicatorEl = document.getElementById('speculative-indicator');
    
    // 初始化场景管理器 (v3.0) - 必须在 ModeSwitch 之前初始化
    if (typeof SceneManager !== 'undefined') {
      SceneManager.init(sessionId, sendWsMessage);
    
      // 监听审题面板的发送请求
      window.addEventListener('scene:send-message', (e) => {
        const { content, scene } = e.detail || {};
        if (content) {
          handleSendMessage(content);
          // 确保场景已切换
          if (scene && SceneManager.getCurrentScene() !== scene) {
            SceneManager.switchScene(scene);
          }
        }
      });

      // 监听用户主动切换场景，清除待显示的场景切换建议
      window.addEventListener('scene:user-switched', () => {
        pendingSceneSwitchHint = null;
      });
    }
    
    // 初始化模式切换模块 - 在 SceneManager 之后初始化
    // 初始化模式切换模块 - 在 SceneManager 之后初始化
    if (typeof ModeSwitch !== 'undefined') {
      ModeSwitch.init({
        sessionId: sessionId,
        sendWsMessage: sendWsMessage,
        onModeChange: handleModeChange
      });
    }

    // ==================== 自定义看板执行分发 ====================
    window.addEventListener('todo:run-task', (e) => {
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'todo_run_task', task_id: e.detail.taskId, group_id: e.detail.groupId }));
        }
    });

    window.addEventListener('todo:run-group', (e) => {
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'todo_confirm', group_id: e.detail.groupId }));
        }
    });
    
    // 初始化待办看板模块 (v3.0)
    if (typeof TodoBoard !== 'undefined') {
      TodoBoard.init(sessionId);
    
      // 监听单任务运行请求（看板内点击"立即执行"触发）
      window.addEventListener('todo:run-task', (e) => {
        const { taskId, groupId } = e.detail || {};
        if (taskId) {
          sendWsMessage({ type: 'todo_run_task', task_id: taskId, group_id: groupId });
        }
      });
    }
    
    // 连接 WebSocket
    connectWebSocket();

    // 更新连接状态 UI
    updateConnectionStatus('connecting');

    // 初始化迷你控制台 (v3.1)
    _initMiniConsole();

    // 初始化工作台操作按钮 (v3.2)
    _initWorkspaceActions();
  });

  // ==================== WebSocket ====================

  function connectWebSocket() {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${protocol}//${location.host}/ws/${sessionId}`;

    try {
      ws = new WebSocket(url);
    } catch (e) {
      console.error('WebSocket 创建失败:', e);
      scheduleReconnect();
      return;
    }

    ws.onopen = () => {
      console.log('[WS] 已连接');
      updateConnectionStatus('connected');
      clearTimeout(reconnectTimer);
      startHeartbeat();
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        handleServerMessage(msg);
      } catch (e) {
        console.warn('[WS] 消息解析失败:', e);
      }
    };

    ws.onclose = (event) => {
      console.warn('[WS] 连接断开:', event.code, event.reason);
      updateConnectionStatus('disconnected');
      stopHeartbeat();
      // 非正常关闭时自动重连
      if (event.code !== 1000) {
        scheduleReconnect();
      }
    };

    ws.onerror = (err) => {
      console.error('[WS] 连接错误:', err);
      updateConnectionStatus('disconnected');
    };
  }

  function scheduleReconnect() {
    clearTimeout(reconnectTimer);
    reconnectTimer = setTimeout(() => {
      console.log('[WS] 尝试重连...');
      updateConnectionStatus('connecting');
      connectWebSocket();
    }, WS_RECONNECT_DELAY);
  }

  function startHeartbeat() {
    stopHeartbeat();
    heartbeatTimer = setInterval(() => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'ping' }));
      }
    }, HEARTBEAT_INTERVAL);
  }

  function stopHeartbeat() {
    if (heartbeatTimer) {
      clearInterval(heartbeatTimer);
      heartbeatTimer = null;
    }
  }

  function sendWsMessage(payload) {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      console.warn('[WS] 连接未就绪，消息丢弃');
      return false;
    }
    ws.send(JSON.stringify(payload));
    return true;
  }

  // ==================== 服务端消息路由 ====================

  function handleServerMessage(msg) {
    const { type } = msg;

    switch (type) {

      case 'connected':
        // 服务端已创建会话
        Sidebar.setCurrentConvId(msg.conversation_id);
        Sidebar.loadConversations();
        break;

      case 'pong':
        // 心跳响应，忽略
        break;

      case 'agent_step':
        if (typeof SceneManager !== 'undefined' && SceneManager.getCurrentScene() !== 'chat') {
          _renderWorkspaceLog(msg);
        } else {
          // Agent 步骤状态更新 → 右侧面板
          if (!isHandlingTask) {
            isHandlingTask = true;
            Panel.show();
            Panel.reset();
          }
          Panel.updateStep(
            msg.step,
            msg.status,
            msg.detail,
            msg.elapsed || null,
            msg.step_id || null,
            msg.parent_id || null
          );
        }
        break;

      case 'agent_params':
        // 任务参数 → 右侧面板参数区
        Panel.showParams(msg.params);
        break;

      case 'speculative_execution':
        // 后台投机执行信号
        if (msg.status === 'start') {
          speculativeIndicatorEl?.classList.remove('hidden');
        } else {
          speculativeIndicatorEl?.classList.add('hidden');
        }
        break;

      case 'debate_stream':
        if (typeof SceneManager !== 'undefined' && SceneManager.getCurrentScene() !== 'chat') {
          _renderWorkspaceLog({
            status: 'running',
            step: msg.role,
            detail: msg.content
          });
        } else {
          // 多角色辩论状态流
          Panel.addDebateBubble(msg.role, msg.avatar, msg.content);
        }
        break;

      case 'response':
        // 最终文本响应 → 主对话区
        // 任何正式响应到达时，关闭投机执行光效
        speculativeIndicatorEl?.classList.add('hidden');

        // 如果有缓存的结果数据，在气泡上附加"查看结果"按钮
        if (lastResult) {
          Chat.showAssistantMessage(msg.content, lastResult);
          lastResult = null;
        } else {
          Chat.showAssistantMessage(msg.content);
        }
        if (!isHandlingTask) isHandlingTask = false;

        // v3.2: 结果输出完毕后，显示待处理的场景切换建议
        if (pendingSceneSwitchHint && typeof SceneManager !== 'undefined') {
          SceneManager.showSwitchHint(pendingSceneSwitchHint);
          pendingSceneSwitchHint = null;
        }
        break;

      case 'result':
        speculativeIndicatorEl?.classList.add('hidden');
        // 结构化结果（有试题生成时）→ 右侧结果面板
        lastResult = {
          markdown: msg.markdown,
          question_count: msg.question_count,
          topic: msg.topic,
          question_type: msg.question_type,
          difficulty: msg.difficulty
        };
        if (typeof SceneManager !== 'undefined' && SceneManager.getCurrentScene() !== 'chat') {
          _renderWorkspaceCanvas(msg.markdown);
        } else {
          Panel.showResult(
            msg.markdown,
            msg.question_count,
            msg.topic,
            msg.question_type,
            msg.difficulty
          );
        }
        isHandlingTask = false;
        break;

      case 'content_preview':
        if (typeof SceneManager !== 'undefined' && SceneManager.getCurrentScene() !== 'chat') {
          _renderWorkspaceCanvas(msg.markdown);
        }
        break;

      case 'error':
        speculativeIndicatorEl?.classList.add('hidden');
        Chat.showErrorMessage(msg.message);
        isHandlingTask = false;
        Panel.markDone();
        break;

      case 'conversation_loaded':
        // 已切换到历史对话 → 恢复消息
        Sidebar.setCurrentConvId(msg.conversation_id);
        Chat.restoreMessages(msg.messages || []);
        Panel.hide();
        Sidebar.loadConversations();
        lastResult = null;
        isHandlingTask = false;
        break;

      case 'conversation_created':
        // 已新建对话
        Sidebar.setCurrentConvId(msg.conversation_id);
        Chat.clearMessages();
        Panel.hide();
        Sidebar.loadConversations();
        lastResult = null;
        break;

      case 'mode_suggest':
        // 模式切换建议 (v2 兼容)
        console.log('[DEBUG] Received mode_suggest:', msg.suggested_mode, msg.transition);
        if (typeof ModeSwitch !== 'undefined') {
          ModeSwitch.handleModeSwitchSignal(msg.suggested_mode, msg.transition);
        }
        break;

      case 'scene_switch_hint':
        // v3.0: Chat Agent 检测到命题/审题意图，存储建议，等待结果输出完毕后显示
        if (msg.scene) {
          pendingSceneSwitchHint = msg.scene;
        }
        break;

      case 'scene_switched':
        // v3.0: 服务端确认场景已切换
        if (typeof SceneManager !== 'undefined' && msg.scene) {
          SceneManager.switchScene(msg.scene);
          // 重置版本历史
          documentVersions = [];
          currentVersionIndex = -1;
        }
        break;

      // ==================== v3.0 待办事件 ====================

      case 'todo_group_created':
        // Planner 生成了任务组 → 渲染看板
        if (typeof TodoBoard !== 'undefined' && msg.group) {
          TodoBoard.renderGroup(msg.group);
        }
        break;

      case 'todo_task_update':
        // 单个任务状态变更
        if (typeof TodoBoard !== 'undefined' && msg.task) {
          TodoBoard.updateTask(msg.task);
        }
        break;

      case 'todo_task_result':
        // 任务执行结果
        if (typeof TodoBoard !== 'undefined' && msg.task_id) {
          TodoBoard.showTaskResult(msg.task_id, msg.result, msg.elapsed_ms);
        }
        break;

      case 'todo_comment_added':
        // 新评论（Agent 添加的）
        if (typeof TodoBoard !== 'undefined' && msg.task_id && msg.comment) {
          TodoBoard.addComment(msg.task_id, msg.comment);
        }
        break;

      // ==================== v3.1 大纲确认 ====================

      case 'outline_confirm_request':
        // 服务端请求用户确认大纲
        if (typeof OutlineConfirm !== 'undefined' && msg.outline) {
          OutlineConfirm.init({
            sendWs: sendWsMessage,
            onConfirm: (outline) => {
              console.log('[App] 大纲已确认:', outline);
            },
            onModify: (outline, feedback) => {
              console.log('[App] 大纲修改请求:', feedback);
            }
          });
          OutlineConfirm.show(msg.outline);
        }
        break;

      case 'outline_updated':
        // 大纲已更新（服务端响应修改请求）
        if (typeof OutlineConfirm !== 'undefined' && msg.outline) {
          OutlineConfirm.show(msg.outline);
        }
        break;

      // ==================== v3.1 事件流协议 ====================

      case 'status_update':
        // 状态更新事件
        if (typeof StatusIndicator !== 'undefined') {
          const statusType = msg.status === 'running' ? 'generating' :
            msg.status === 'done' ? 'idle' : 'thinking';
          StatusIndicator.setStatus(statusType, msg.message || msg.step);
          if (msg.progress !== undefined) {
            StatusIndicator.setProgress(msg.progress);
          }
        }
        break;

      case 'tool_call':
        // 工具调用事件
        if (typeof ThoughtChain !== 'undefined') {
          const toolStepId = ThoughtChain.addStep({
            type: 'action',
            title: `调用工具: ${msg.tool_name || '未知'}`,
            content: msg.arguments ? JSON.stringify(msg.arguments, null, 2) : '',
            status: 'running'
          });
          // 缓存 stepId 用于 tool_result 时更新
          if (!window._toolCallMap) window._toolCallMap = {};
          window._toolCallMap[msg.call_id] = toolStepId;
        }
        break;

      case 'tool_result':
        // 工具返回结果
        if (typeof ThoughtChain !== 'undefined' && window._toolCallMap) {
          const stepId = window._toolCallMap[msg.call_id];
          if (stepId) {
            ThoughtChain.completeStep(stepId,
              msg.result ? JSON.stringify(msg.result, null, 2) : '完成',
              msg.elapsed_ms
            );
            delete window._toolCallMap[msg.call_id];
          }
        }
        break;

      case 'content_delta':
        // 内容增量流式传输
        const canvas = document.getElementById('workspace-canvas-content');
        if (canvas && msg.content) {
          // 追加内容到画布
          const currentContent = canvas.dataset.rawContent || '';
          const newContent = currentContent + msg.content;
          canvas.dataset.rawContent = newContent;

          // 渲染 Markdown
          if (window.marked) {
            canvas.innerHTML = marked.parse(newContent);
            if (window.hljs) {
              canvas.querySelectorAll('pre code').forEach(block => hljs.highlightElement(block));
            }
          } else {
            canvas.textContent = newContent;
          }

          // 滚动到底部
          canvas.scrollTop = canvas.scrollHeight;
        }
        break;

      case 'interrupt_request':
        // Agent 请求用户确认
        const interruptCard = document.createElement('div');
        interruptCard.className = 'interrupt-card';
        interruptCard.innerHTML = `
          <div class="interrupt-header">
            <div class="interrupt-icon">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fbbf24" stroke-width="2">
                <circle cx="12" cy="12" r="10"></circle>
                <line x1="12" y1="8" x2="12" y2="12"></line>
                <line x1="12" y1="16" x2="12.01" y2="16"></line>
              </svg>
            </div>
            <span class="interrupt-title">需要您的确认</span>
          </div>
          <div class="interrupt-question">${msg.question || '请确认是否继续？'}</div>
          <div class="interrupt-actions">
            <button class="interrupt-btn interrupt-btn-secondary" data-action="cancel">取消</button>
            <button class="interrupt-btn interrupt-btn-primary" data-action="confirm">确认</button>
          </div>
        `;

        // 添加到工作台日志
        const logContainer = document.getElementById('workspace-activity-log');
        if (logContainer) {
          logContainer.appendChild(interruptCard);
          interruptCard.scrollIntoView({ behavior: 'smooth' });
        }

        // 绑定按钮事件
        interruptCard.querySelectorAll('.interrupt-btn').forEach(btn => {
          btn.addEventListener('click', () => {
            const action = btn.dataset.action;
            sendWsMessage({
              type: 'interrupt_response',
              request_id: msg.request_id,
              action: action
            });
            interruptCard.remove();
          });
        });
        break;

      default:
        console.debug('[WS] 未知消息类型:', type, msg);
    }
  }

  // ==================== 用户操作处理 ====================

  /** 发送用户消息 (支持重生成标志) */
  function handleSendMessage(content, isRegenerate = false) {
    if (!content) return;

    // 检查 WebSocket 是否就绪
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      Chat.showErrorMessage('连接断开，正在重连，请稍后重试。');
      connectWebSocket();
      return;
    }

    if (!isRegenerate) {
      // 正常发送，渲染用户消息气泡
      Chat.appendUserMessage(content);
    } else {
      // 重新生成，设置 Chat 内部状态
      Chat.setRegenerating(true);
    }

    // 显示打字动画（如果重生成，动画应该是替换原AI气泡或在其下方）
    Chat.showTyping(isRegenerate);

    // 清空执行日志，为新任务做准备
    if (typeof ThoughtChain !== 'undefined') {
      ThoughtChain.clear();
    }

    // 通知服务端开始任务（面板将在收到第一个 agent_step 时打开）
    isHandlingTask = false;  // 先重置，agent_step 到来时再设为 true

    // 发送到服务端 (后端逻辑不变，依然当做一次 user message 接收，但前端不重复画 user 气泡)
    sendWsMessage({ type: 'message', content });
  }

  /** 切换/新建对话 */
  function handleSwitchConversation(convId) {
    isHandlingTask = false;
    Panel.hide();
    lastResult = null;

    if (convId) {
      // 切换到已有对话
      sendWsMessage({ type: 'switch_conversation', conversation_id: convId });
    } else {
      // 新建对话
      sendWsMessage({ type: 'switch_conversation', conversation_id: '' });
    }
  }

  /** 重新展示右侧结果面板（"查看结果"按钮触发） */
  function handleShowResult(resultData) {
    if (!resultData) return;
    Panel.show();
    Panel.showResultData(resultData);
  }

  /** 模式切换回调 */
  function handleModeChange(mode, transition) {
    console.log('[App] 模式切换:', mode, transition);
    // 可以在这里添加模式切换后的额外逻辑
  }

  // ==================== 状态 UI ====================

  function updateConnectionStatus(state) {
    const dot = document.getElementById('connection-status');
    if (!dot) return;
    dot.className = `status-dot ${state}`;
    dot.title = {
      connected: '已连接',
      disconnected: '连接断开',
      connecting: '正在连接...'
    }[state] || '';
  }

  // ==================== 工作台视图渲染函数 (v3.1) ====================

  function _renderWorkspaceLog(msg) {
    const logContainer = document.getElementById('workspace-activity-log');
    if (!logContainer) return;

    // 初始化思考链组件（如果尚未初始化）
    if (typeof ThoughtChain !== 'undefined' && !logContainer.querySelector('.thought-chain-container')) {
      ThoughtChain.init('workspace-activity-log');
    }

    // 使用思考链组件渲染
    if (typeof ThoughtChain !== 'undefined') {
      const stepTitle = msg.step || 'Agent Action';

      // 检查是否已存在相同标题的步骤
      const existingStep = ThoughtChain.findStepByTitle(stepTitle);

      if (existingStep) {
        // 已存在，更新步骤状态
        ThoughtChain.updateStep(existingStep.id, {
          status: msg.status || 'running',
          content: msg.detail || ''
        });

        // 如果是完成状态，添加耗时
        if (msg.status === 'done' && msg.elapsed) {
          ThoughtChain.updateStep(existingStep.id, {
            elapsed: `${parseFloat(msg.elapsed).toFixed(1)}s`
          });
        }
      } else {
        // 不存在，创建新步骤
        const stepType = msg.step?.includes('工具') || msg.step?.includes('调用') ? 'action' :
          msg.step?.includes('思考') ? 'thought' :
            msg.step?.includes('观察') ? 'observation' : 'thought';

        const stepId = `step_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;

        ThoughtChain.addStep({
          id: stepId,
          type: stepType,
          title: stepTitle,
          content: msg.detail || '',
          status: msg.status || 'running'
        });

        // 如果是完成状态，更新耗时
        if (msg.status === 'done' && msg.elapsed) {
          ThoughtChain.updateStep(stepId, {
            elapsed: `${parseFloat(msg.elapsed).toFixed(1)}s`
          });
        }
      }
      return;
    }

    // 降级渲染（如果 ThoughtChain 不可用）
    const logItem = document.createElement('div');
    logItem.className = `log-item ${msg.status || 'info'}`;
    logItem.style.padding = '8px 12px';
    logItem.style.background = 'rgba(255,255,255,0.05)';
    logItem.style.borderRadius = '6px';
    logItem.style.fontSize = '12px';

    let icon = '🔄';
    if (msg.status === 'done') icon = '✅';
    if (msg.status === 'error') icon = '❌';

    logItem.innerHTML = `
      <div style="font-weight: 600; margin-bottom: 4px; display: flex; align-items: center; gap: 6px;">
        <span>${icon}</span>
        <span>${msg.step || 'Agent Action'}</span>
      </div>
      <div style="color: var(--text-secondary); white-space: pre-wrap; padding-left: 22px;">${msg.detail || ''}</div>
    `;
    logContainer.appendChild(logItem);
    logContainer.scrollTop = logContainer.scrollHeight;
  }

  function _renderWorkspaceCanvas(markdown) {
    if (typeof SceneManager !== 'undefined' && SceneManager.getCurrentScene() === 'review') {
      if (typeof AuditView !== 'undefined') {
        AuditView.render(markdown, 'workspace-canvas-content');
        return;
      }
    }

    const canvas = document.getElementById('workspace-canvas-content');
    if (!canvas) return;

    // 保存到历史版本（如果有内容变化）
    if (markdown && markdown.trim()) {
      const newVersion = {
        markdown: markdown,
        timestamp: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }),
        preview: markdown.substring(0, 50) + '...'
      };

      // 检查是否与上一版本相同
      const lastVersion = documentVersions[documentVersions.length - 1];
      if (!lastVersion || lastVersion.markdown !== markdown) {
        documentVersions.push(newVersion);
        currentVersionIndex = documentVersions.length - 1;
        _updateVersionBar();
      }
    }

    // 渲染 Markdown
    if (window.marked) {
      canvas.innerHTML = marked.parse(markdown);
      if (window.hljs) {
        canvas.querySelectorAll('pre code').forEach(block => hljs.highlightElement(block));
      }
    } else {
      canvas.textContent = markdown;
    }
  }

  // 更新版本切换栏
  function _updateVersionBar() {
    let versionBar = document.getElementById('document-version-bar');
    const canvasContainer = document.getElementById('workspace-canvas-content');
    if (!canvasContainer) return;

    // 如果没有版本栏，创建一个
    if (!versionBar) {
      versionBar = document.createElement('div');
      versionBar.id = 'document-version-bar';
      versionBar.className = 'version-bar';
      canvasContainer.parentNode.insertBefore(versionBar, canvasContainer);
    }

    // 只有一个版本时隐藏
    if (documentVersions.length <= 1) {
      versionBar.style.display = 'none';
      return;
    }

    versionBar.style.display = 'flex';
    versionBar.innerHTML = `
      <button class="version-nav-btn" id="version-prev" ${currentVersionIndex <= 0 ? 'disabled' : ''}>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="15 18 9 12 15 6"></polyline>
        </svg>
      </button>
      <span class="version-info">版本 ${currentVersionIndex + 1} / ${documentVersions.length}</span>
      <span class="version-time">${documentVersions[currentVersionIndex]?.timestamp || ''}</span>
      <button class="version-nav-btn" id="version-next" ${currentVersionIndex >= documentVersions.length - 1 ? 'disabled' : ''}>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="9 18 15 12 9 6"></polyline>
        </svg>
      </button>
    `;

    // 绑定切换事件
    versionBar.querySelector('#version-prev')?.addEventListener('click', () => {
      if (currentVersionIndex > 0) {
        currentVersionIndex--;
        _showVersion(currentVersionIndex);
      }
    });

    versionBar.querySelector('#version-next')?.addEventListener('click', () => {
      if (currentVersionIndex < documentVersions.length - 1) {
        currentVersionIndex++;
        _showVersion(currentVersionIndex);
      }
    });
  }

  // 显示指定版本
  function _showVersion(index) {
    const version = documentVersions[index];
    if (!version) return;

    const canvas = document.getElementById('workspace-canvas-content');
    if (!canvas) return;

    if (window.marked) {
      canvas.innerHTML = marked.parse(version.markdown);
      if (window.hljs) {
        canvas.querySelectorAll('pre code').forEach(block => hljs.highlightElement(block));
      }
    } else {
      canvas.textContent = version.markdown;
    }

    _updateVersionBar();
  }

  // ==================== 迷你控制台 (v3.1) ====================

  function _initMiniConsole() {
    const toggleBtn = document.getElementById('mini-console-toggle');
    const body = document.getElementById('mini-console-body');
    const input = document.getElementById('mini-console-input');
    const sendBtn = document.getElementById('mini-console-send');
    const suggestionChips = document.querySelectorAll('.suggestion-chip');

    if (!toggleBtn || !body) return;

    // 切换展开/收起
    toggleBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      body.classList.toggle('collapsed');
      toggleBtn.classList.toggle('collapsed');
    });

    // 发送消息
    function sendMiniMessage() {
      const content = input?.value?.trim();
      if (!content) return;

      // 检查 WebSocket 是否就绪
      if (!ws || ws.readyState !== WebSocket.OPEN) {
        Chat.showErrorMessage('连接断开，正在重连，请稍后重试。');
        connectWebSocket();
        return;
      }

      // 清空执行日志，为新任务做准备
      if (typeof ThoughtChain !== 'undefined') {
        ThoughtChain.clear();
      }

      // 重置任务处理状态
      isHandlingTask = false;

      // 发送到服务端
      sendWsMessage({ type: 'message', content });

      // 清空输入
      if (input) input.value = '';

      // 在工作台日志中显示用户指令
      _renderWorkspaceLog({
        status: 'info',
        step: '👤 用户指令',
        detail: content
      });
    }

    sendBtn?.addEventListener('click', sendMiniMessage);
    input?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMiniMessage();
      }
    });

    // 建议芯片点击
    suggestionChips.forEach(chip => {
      chip.addEventListener('click', () => {
        const prompt = chip.dataset.prompt;
        if (prompt) {
          if (input) input.value = prompt;
          sendMiniMessage();
        }
      });
    });
  }

  function _initWorkspaceActions() {
    const downloadBtn = document.getElementById('workspace-download-btn');
    const downloadOptions = document.getElementById('download-options');
    const copyBtn = document.getElementById('workspace-copy-btn');
    
    // Toggle Dropdown
    downloadBtn?.addEventListener('click', (e) => {
        e.stopPropagation();
        if (downloadOptions) {
            downloadOptions.style.display = downloadOptions.style.display === 'none' ? 'block' : 'none';
        }
    });
    document.addEventListener('click', () => {
        if (downloadOptions) downloadOptions.style.display = 'none';
    });
    
    // Handle Dropdown clicks
    downloadOptions?.querySelectorAll('.dropdown-item').forEach(item => {
        item.addEventListener('click', (e) => {
            e.stopPropagation();
            downloadOptions.style.display = 'none';
            const format = item.dataset.format;
            _executeDownload(format);
        });
    });

    // 下载核心逻辑
    function _executeDownload(format) {
      // 获取当前版本的内容
      const content = documentVersions[currentVersionIndex]?.markdown || '';
      if (!content) {
        alert('暂无内容可下载');
        return;
      }

      const scene = SceneManager?.getCurrentScene() || 'document';
      const sceneName = scene === 'proposition' ? '试卷' : scene === 'review' ? '审题报告' : '文档';
      const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
      const filename = `${sceneName}_${timestamp}`;
      
      let blob, url;
      
      if (format === 'md') {
          // 直接下载 MD
          blob = new Blob([content], { type: 'text/markdown;charset=utf-8' });
          url = URL.createObjectURL(blob);
          _triggerDownloadLink(url, `${filename}.md`);
      } else if (format === 'docx') {
          const htmlContent = window.marked ? marked.parse(content) : content;
          const fullHtml = `<!DOCTYPE html><html><head><meta charset="utf-8"><title>${sceneName}</title><style>body{font-family:"Microsoft YaHei",sans-serif;}</style></head><body>${htmlContent}</body></html>`;
          
          if (typeof htmlDocx !== 'undefined') {
              // 使用真实 docx 生成库
              blob = htmlDocx.asBlob(fullHtml);
              url = URL.createObjectURL(blob);
              _triggerDownloadLink(url, `${filename}.docx`);
          } else {
              // Fallback
              const preHtml = "<html xmlns:o='urn:schemas-microsoft-com:office:office' xmlns:w='urn:schemas-microsoft-com:office:word' xmlns='http://www.w3.org/TR/REC-html40'><head><meta charset='utf-8'><title>Document</title></head><body>";
              blob = new Blob(['\ufeff', preHtml, htmlContent, "</body></html>"], { type: 'application/msword;charset=utf-8' });
              url = URL.createObjectURL(blob);
              _triggerDownloadLink(url, `${filename}.doc`);
          }
      } else if (format === 'pdf') {
          // 通过 iframe 调用 window.print 生成 PDF
          const htmlContent = window.marked ? marked.parse(content) : content;
          const iframe = document.createElement('iframe');
          iframe.style.display = 'none';
          document.body.appendChild(iframe);
          iframe.contentDocument.write(`<html><head><meta charset="utf-8">
            <style>body{font-family: sans-serif; padding: 20px;} pre{background:#f4f4f4;padding:10px;white-space:pre-wrap;} img{max-width:100%;}</style>
            </head><body>${htmlContent}</body></html>`);
          iframe.contentDocument.close();
          iframe.contentWindow.focus();
          setTimeout(() => {
              iframe.contentWindow.print();
              setTimeout(() => document.body.removeChild(iframe), 1000);
          }, 500);
          return; // print 没法获取准确成功状态，直接返回
      }

      // 显示成功提示
      const originalHtml = downloadBtn.innerHTML;
      downloadBtn.innerHTML = `
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"></polyline></svg>
        <span style="font-size:12px;">已导出${format.toUpperCase()}</span>
      `;
      setTimeout(() => { downloadBtn.innerHTML = originalHtml; }, 2000);
    }
    
    function _triggerDownloadLink(url, filename) {
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }

    // 复制内容
    copyBtn?.addEventListener('click', () => {
      const content = documentVersions[currentVersionIndex]?.markdown || '';
      if (!content) {
        alert('暂无内容可复制');
        return;
      }

      navigator.clipboard.writeText(content).then(() => {
        // 显示成功提示
        copyBtn.innerHTML = `
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="20 6 9 17 4 12"></polyline>
          </svg>
        `;
        copyBtn.title = '已复制';
        setTimeout(() => {
          copyBtn.innerHTML = `
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="9" y="9" width="13" height="13" rx="2"></rect>
              <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"></path>
            </svg>
          `;
          copyBtn.title = '复制内容';
        }, 2000);
      });
    });
  }

  // ==================== 工具函数 ====================

  function generateId() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
      const r = (Math.random() * 16) | 0;
      const v = c === 'x' ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  }

})();
