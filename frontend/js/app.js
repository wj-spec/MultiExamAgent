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

  // ==================== 初始化 ====================

  document.addEventListener('DOMContentLoaded', () => {
    // 初始化各模块
    Panel.init();
    Sidebar.init(handleSwitchConversation);
    Chat.init(handleSendMessage, handleShowResult);

    speculativeIndicatorEl = document.getElementById('speculative-indicator');

    // 初始化模式切换模块
    if (typeof ModeSwitch !== 'undefined') {
      ModeSwitch.init({
        sessionId: sessionId,
        onModeChange: handleModeChange
      });
    }

    // 连接 WebSocket
    connectWebSocket();

    // 更新连接状态 UI
    updateConnectionStatus('connecting');
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
        // 多角色辩论状态流
        Panel.addDebateBubble(msg.role, msg.avatar, msg.content);
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
        Panel.showResult(
          msg.markdown,
          msg.question_count,
          msg.topic,
          msg.question_type,
          msg.difficulty
        );
        isHandlingTask = false;
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
        // 模式切换建议
        console.log('[DEBUG] Received mode_suggest:', msg.suggested_mode, msg.transition);
        if (typeof ModeSwitch !== 'undefined') {
          ModeSwitch.handleModeSwitchSignal(msg.suggested_mode, msg.transition);
        } else {
          console.error('[DEBUG] ModeSwitch module not loaded!');
        }
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

  // ==================== 工具函数 ====================

  function generateId() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
      const r = (Math.random() * 16) | 0;
      const v = c === 'x' ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  }

})();
