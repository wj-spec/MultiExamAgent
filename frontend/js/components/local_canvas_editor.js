/**
 * local_canvas_editor.js
 * 实现划词选中局部重写组件
 */
document.addEventListener('DOMContentLoaded', () => {
    // 创建悬浮工具栏
    const tooltip = document.createElement('div');
    tooltip.className = 'canvas-editor-tooltip';
    tooltip.innerHTML = `
        <button id="canvas-rewrite-btn">✨ 局部重写</button>
    `;
    document.body.appendChild(tooltip);

    // 创建输入框弹窗
    const dialog = document.createElement('div');
    dialog.className = 'canvas-editor-dialog';
    dialog.innerHTML = `
        <div class="canvas-editor-header">针对选中文本提出修改要求：</div>
        <textarea id="canvas-instruction-input" placeholder="例如：让这段话的语气更幽默..."></textarea>
        <div class="canvas-editor-footer">
            <button id="canvas-cancel-btn">取消</button>
            <button id="canvas-submit-btn">提交给 Agent</button>
        </div>
    `;
    document.body.appendChild(dialog);

    let currentSelection = '';
    let currentTaskElement = null;

    // 监听选中文本
    document.addEventListener('mouseup', (e) => {
        // 如果点击的是弹窗或悬浮窗内部，忽略
        if (tooltip.contains(e.target) || dialog.contains(e.target)) return;

        const selection = window.getSelection();
        const text = selection.toString().trim();
        
        // 限制只在 todo board 的 markdown 结果区域内生效
        const resultContainer = e.target.closest('.todo-card-result-markdown');
        
        if (text.length > 0 && resultContainer) {
            currentSelection = text;
            currentTaskElement = e.target.closest('.todo-card');
            
            // 定位悬浮窗
            const range = selection.getRangeAt(0);
            const rect = range.getBoundingClientRect();
            
            tooltip.style.left = `${rect.left + window.scrollX + (rect.width / 2) - (tooltip.offsetWidth / 2)}px`;
            tooltip.style.top = `${rect.top + window.scrollY - 40}px`;
            tooltip.style.display = 'block';
        } else {
            tooltip.style.display = 'none';
        }
    });

    // 点击局部重写
    document.getElementById('canvas-rewrite-btn').addEventListener('click', () => {
        tooltip.style.display = 'none';
        
        // 居中显示弹窗
        dialog.style.display = 'block';
        dialog.style.left = '50%';
        dialog.style.top = '50%';
        dialog.style.transform = 'translate(-50%, -50%)';
        
        document.getElementById('canvas-instruction-input').focus();
    });

    // 取消重写
    document.getElementById('canvas-cancel-btn').addEventListener('click', () => {
        dialog.style.display = 'none';
        document.getElementById('canvas-instruction-input').value = '';
        window.getSelection().removeAllRanges();
    });

    // 提交重写请求
    document.getElementById('canvas-submit-btn').addEventListener('click', async () => {
        const instruction = document.getElementById('canvas-instruction-input').value.trim();
        if (!instruction || !currentTaskElement) return;

        const taskId = currentTaskElement.dataset.taskId;
        
        // 发送局部修改请求到后端接口 (对应 Phase 2.3)
        console.log(`[Canvas Editor] Task ${taskId}: Rewriting "${currentSelection}" -> Instruction: ${instruction}`);
        
        // 模拟提交完成
        dialog.style.display = 'none';
        document.getElementById('canvas-instruction-input').value = '';
        window.getSelection().removeAllRanges();
        
        // 通知外部或改变卡片状态为 running
        window.dispatchEvent(new CustomEvent('todo:local-rewrite', {
            detail: { taskId, selection: currentSelection, instruction }
        }));
    });
});
