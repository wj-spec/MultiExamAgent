/**
 * mode_switch.js - 模式切换模块
 * 
 * 功能：
 * 1. 右上角模式切换按钮
 * 2. 自动模式切换（直接切换，无弹窗）
 * 3. 专业模式顶栏显示
 */

const ModeSwitch = (() => {
    // 状态
    let currentMode = 'chat';
    let sessionId = null;

    // DOM 元素
    let modeSwitcher, currentModeText, modeButtons;

    // 回调
    let onModeChange = null;

    /**
     * 初始化
     */
    function init(options = {}) {
        sessionId = options.sessionId || generateSessionId();
        onModeChange = options.onModeChange || null;

        // 获取 DOM 元素
        modeSwitcher = document.getElementById('mode-switcher');
        currentModeText = document.getElementById('current-mode');
        modeButtons = {
            chat: document.getElementById('btn-mode-chat'),
            proposition: document.getElementById('btn-mode-proposition'),
            grading: document.getElementById('btn-mode-grading')
        };

        // 专业模式顶栏
        // 已移除，模式切换完全由右上角按钮控制

        // 绑定事件
        bindEvents();

        // 加载保存的状态
        loadSavedState();
    }

    /**
     * 绑定事件
     */
    function bindEvents() {
        // 模式切换按钮
        Object.keys(modeButtons).forEach(mode => {
            const btn = modeButtons[mode];
            if (btn) {
                btn.addEventListener('click', () => handleModeButtonClick(mode));
            }
        });

        // 快捷键
        document.addEventListener('keydown', (e) => {
            if (e.ctrlKey || e.metaKey) {
                if (e.key === 'm') {
                    e.preventDefault();
                    toggleMode();
                } else if (e.key === '1') {
                    e.preventDefault();
                    switchToMode('chat');
                } else if (e.key === '2') {
                    e.preventDefault();
                    switchToMode('proposition');
                } else if (e.key === '3') {
                    e.preventDefault();
                    switchToMode('grading');
                }
            }
        });
    }

    /**
     * 处理模式按钮点击
     */
    async function handleModeButtonClick(mode) {
        if (mode === currentMode) return;
        await switchToMode(mode);
    }

    /**
     * 切换到指定模式
     */
    async function switchToMode(mode) {
        try {
            const response = await fetch('/api/mode/switch', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: sessionId,
                    mode: mode,
                    auto: false
                })
            });

            const result = await response.json();

            if (result.success) {
                currentMode = mode;
                updateUI();
                saveState();

                if (onModeChange) {
                    onModeChange(mode, result.transition);
                }
            }

        } catch (error) {
            console.error('[ModeSwitch] 切换模式失败:', error);
        }
    }

    /**
     * 切换模式（循环）
     */
    function toggleMode() {
        const modes = ['chat', 'proposition', 'grading'];
        const currentIndex = modes.indexOf(currentMode);
        const nextIndex = (currentIndex + 1) % modes.length;
        switchToMode(modes[nextIndex]);
    }

    /**
     * 更新 UI
     */
    function updateUI() {
        // 更新模式按钮状态
        Object.keys(modeButtons).forEach(mode => {
            const btn = modeButtons[mode];
            if (btn) {
                btn.classList.toggle('active', mode === currentMode);
            }
        });

        // 更新当前模式文本
        const modeNames = {
            chat: '基础模式',
            proposition: '命题模式',
            grading: '审卷模式'
        };

        if (currentModeText) {
            currentModeText.textContent = modeNames[currentMode] || currentMode;
        }

        // 更新页面主题类
        document.body.classList.remove('mode-chat', 'mode-proposition', 'mode-grading');
        document.body.classList.add(`mode-${currentMode}`);
    }

    /**
     * 保存状态
     */
    function saveState() {
        try {
            localStorage.setItem('mode_switch_state', JSON.stringify({
                currentMode,
                sessionId
            }));
        } catch (e) {
            // 忽略存储错误
        }
    }

    /**
     * 加载保存的状态
     */
    function loadSavedState() {
        try {
            const saved = localStorage.getItem('mode_switch_state');
            if (saved) {
                const state = JSON.parse(saved);
                // 恢复模式
                if (state.currentMode && state.currentMode !== 'chat') {
                    switchToMode(state.currentMode);
                }
            }
        } catch (e) {
            // 忽略
        }
    }

    /**
     * 生成会话 ID
     */
    function generateSessionId() {
        return 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    }

    /**
     * 获取当前模式
     */
    function getCurrentMode() {
        return currentMode;
    }

    /**
     * 处理后端返回的模式切换信号
     * 简化逻辑：直接切换模式，不弹窗确认
     */
    function handleModeSwitchSignal(mode, transition) {
        console.log('[ModeSwitch] Auto switching to mode:', mode);
        // 直接切换模式，不弹窗
        if (mode) {
            switchToMode(mode);
        }
    }

    // 公开 API
    return {
        init,
        switchToMode,
        toggleMode,
        getCurrentMode,
        handleModeSwitchSignal
    };
})();

// 导出
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ModeSwitch;
}
