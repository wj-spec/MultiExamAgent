/**
 * voice_input.js — 语音输入模块
 *
 * 使用 MediaRecorder API 录制音频，发送到后端 /api/asr，
 * 将识别结果填入聊天输入框。
 */

const VoiceInput = (() => {
    let mediaRecorder = null;
    let audioChunks = [];
    let isRecording = false;
    let micBtn = null;
    let chatInput = null;

    /* ---- 状态常量 ---- */
    const STATE = { IDLE: 'idle', RECORDING: 'recording', PROCESSING: 'processing' };
    let currentState = STATE.IDLE;

    function setState(s) {
        currentState = s;
        if (!micBtn) return;

        micBtn.classList.remove('mic-recording', 'mic-processing');
        micBtn.disabled = false;

        if (s === STATE.RECORDING) {
            micBtn.classList.add('mic-recording');
            micBtn.title = '点击停止录音';
        } else if (s === STATE.PROCESSING) {
            micBtn.classList.add('mic-processing');
            micBtn.title = '识别中...';
            micBtn.disabled = true;
        } else {
            micBtn.title = '语音输入';
        }
    }

    /* ---- 开始录音 ---- */
    async function startRecording() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

            // 选择支持的 MIME type
            const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
                ? 'audio/webm;codecs=opus'
                : MediaRecorder.isTypeSupported('audio/webm')
                    ? 'audio/webm'
                    : 'audio/ogg';

            mediaRecorder = new MediaRecorder(stream, { mimeType });
            audioChunks = [];

            mediaRecorder.addEventListener('dataavailable', (e) => {
                if (e.data.size > 0) audioChunks.push(e.data);
            });

            mediaRecorder.addEventListener('stop', async () => {
                // 停止所有音频轨道
                stream.getTracks().forEach(t => t.stop());
                await processAudio(mimeType);
            });

            mediaRecorder.start(100); // 每100ms产生一个数据块
            setState(STATE.RECORDING);
            isRecording = true;

        } catch (err) {
            console.error('麦克风权限被拒绝:', err);
            showToast('⚠️ 无法访问麦克风，请检查浏览器权限设置');
            setState(STATE.IDLE);
        }
    }

    /* ---- 停止录音 ---- */
    function stopRecording() {
        if (mediaRecorder && mediaRecorder.state !== 'inactive') {
            mediaRecorder.stop();
            isRecording = false;
            setState(STATE.PROCESSING);
        }
    }

    /* ---- 处理音频并发送 ---- */
    async function processAudio(mimeType) {
        const blob = new Blob(audioChunks, { type: mimeType });

        if (blob.size < 1000) {
            // 音频太短，忽略
            setState(STATE.IDLE);
            return;
        }

        try {
            const formData = new FormData();
            const ext = mimeType.includes('webm') ? 'webm' : 'ogg';
            formData.append('file', blob, `voice.${ext}`);

            const res = await fetch('/api/asr', {
                method: 'POST',
                body: formData
            });

            const data = await res.json();

            if (data.success && data.text) {
                // 将识别文字插入输入框
                if (chatInput) {
                    const cur = chatInput.value;
                    const sep = cur && !cur.endsWith(' ') ? ' ' : '';
                    chatInput.value = cur + sep + data.text;
                    chatInput.dispatchEvent(new Event('input')); // 触发自动高度调整
                    chatInput.focus();
                }
                showToast(`🎤 "${data.text.slice(0, 30)}${data.text.length > 30 ? '…' : ''}"`);
            } else if (!data.success) {
                showToast(`⚠️ 识别失败: ${(data.error || '未知错误').slice(0, 60)}`);
            } else {
                showToast('🎤 未识别到语音内容');
            }
        } catch (err) {
            console.error('ASR 请求失败:', err);
            showToast('⚠️ 语音识别服务暂不可用');
        } finally {
            setState(STATE.IDLE);
        }
    }

    /* ---- 简易 Toast 提示 ---- */
    function showToast(msg) {
        let toast = document.getElementById('voice-toast');
        if (!toast) {
            toast = document.createElement('div');
            toast.id = 'voice-toast';
            toast.className = 'voice-toast';
            document.body.appendChild(toast);
        }
        toast.textContent = msg;
        toast.classList.add('visible');
        clearTimeout(toast._timer);
        toast._timer = setTimeout(() => toast.classList.remove('visible'), 3000);
    }

    /* ---- 切换录音 ---- */
    function toggle() {
        if (currentState === STATE.RECORDING) {
            stopRecording();
        } else if (currentState === STATE.IDLE) {
            startRecording();
        }
    }

    /* ---- 初始化 ---- */
    function init() {
        micBtn = document.getElementById('mic-btn');
        chatInput = document.getElementById('chat-input');

        if (!micBtn) return;

        // 检查浏览器支持
        if (!navigator.mediaDevices || !MediaRecorder) {
            micBtn.title = '当前浏览器不支持语音输入';
            micBtn.style.opacity = '0.4';
            micBtn.style.cursor = 'not-allowed';
            return;
        }

        micBtn.addEventListener('click', toggle);
    }

    return { init };
})();

document.addEventListener('DOMContentLoaded', () => VoiceInput.init());
