// ── View elements ──────────────────────────────────────────
const galleryView = document.getElementById('gallery-view');
const recordView = document.getElementById('record-view');
const detailView = document.getElementById('detail-view');
const searchView = document.getElementById('search-view');

const taskListEl = document.getElementById('task-list');
const newMeetingBtn = document.getElementById('new-meeting-btn');
const homeBtn = document.getElementById('home-btn');

const recordBtn = document.getElementById('record-btn');
const statusText = document.getElementById('status-text');
const timerEl = document.getElementById('timer');
const chunkCount = document.getElementById('chunk-count');
const transcriptEl = document.getElementById('transcript');
const minutesEl = document.getElementById('minutes');
const knowledgeEl = document.getElementById('knowledge');
const knowledgeCount = document.getElementById('knowledge-count');

const detailTitle = document.getElementById('detail-title');
const detailMeta = document.getElementById('detail-meta');
const detailTranscript = document.getElementById('detail-transcript');
const detailMinutes = document.getElementById('detail-minutes');
const detailKnowledge = document.getElementById('detail-knowledge');
const detailKnowledgeCount = document.getElementById('detail-knowledge-count');
const detailBackBtn = document.getElementById('detail-back-btn');

const searchBtn = document.getElementById('search-btn');
const backBtn = document.getElementById('back-btn');
const doSearchBtn = document.getElementById('do-search');
const searchQuery = document.getElementById('search-query');
const searchResults = document.getElementById('search-results');

// ── View switching ─────────────────────────────────────────
function showView(view) {
    [galleryView, recordView, detailView, searchView].forEach(v => v.classList.add('hidden'));
    view.classList.remove('hidden');
}

// ── Task Gallery ───────────────────────────────────────────
function formatDuration(seconds) {
    if (!seconds || seconds === 0) return '--';
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}m${s}s`;
}

function formatTime(iso) {
    if (!iso) return '--';
    try {
        const d = new Date(iso);
        return d.toLocaleString('zh-CN', {month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit'});
    } catch {
        return iso.substring(0, 16);
    }
}

function statusBadge(status) {
    const map = {
        'recording': '<span class="badge badge-recording">录音中</span>',
        'stopped': '<span class="badge badge-stopped">已完成</span>',
        'completed': '<span class="badge badge-completed">已完成</span>',
    };
    return map[status] || `<span class="badge">${status}</span>`;
}

async function loadTaskList() {
    try {
        const resp = await fetch('/api/tasks');
        const data = await resp.json();
        const tasks = data.tasks || [];
        if (tasks.length === 0) {
            taskListEl.innerHTML = '<p class="empty-hint">暂无会议转录任务，点击「新建会议转录」开始。</p>';
            return;
        }
        taskListEl.innerHTML = '';
        tasks.forEach(t => {
            const card = document.createElement('div');
            card.className = 'task-card';
            card.innerHTML = `
                <div class="task-card-header">
                    <span class="task-card-title">${t.title || '(未命名)'}</span>
                    ${statusBadge(t.status)}
                </div>
                <div class="task-card-meta">
                    <span>📅 ${formatTime(t.started_at)}</span>
                    <span>⏱ ${formatDuration(t.duration)}</span>
                    <span>🎙 ${t.chunk_count || 0} 片段</span>
                </div>
                <div class="task-card-participants">${t.participants || '--'}</div>
                <button class="task-card-btn" data-id="${t.id}">查看详情</button>
            `;
            taskListEl.appendChild(card);
        });
        taskListEl.querySelectorAll('.task-card-btn').forEach(btn => {
            btn.addEventListener('click', () => loadTaskDetail(btn.dataset.id));
        });
    } catch (e) {
        taskListEl.innerHTML = '<p class="error">加载失败: ' + e.message + '</p>';
    }
}

// ── Task Detail ────────────────────────────────────────────
async function loadTaskDetail(taskId) {
    showView(detailView);
    detailTitle.textContent = '加载中...';
    detailMeta.textContent = '';
    detailTranscript.textContent = '';
    detailMinutes.textContent = '';
    detailKnowledge.innerHTML = '';
    detailKnowledgeCount.textContent = '(0)';

    try {
        const resp = await fetch(`/api/tasks/${taskId}`);
        if (!resp.ok) {
            detailTitle.textContent = '任务不存在';
            return;
        }
        const t = await resp.json();
        detailTitle.textContent = t.title || '(未命名)';
        detailMeta.innerHTML = `
            ${statusBadge(t.status)}
            <span>📅 ${formatTime(t.started_at)}</span>
            <span>⏱ ${formatDuration(t.duration)}</span>
            <span>🎙 ${t.chunk_count || 0} 片段</span>
            <span>👥 ${t.participants || '--'}</span>
        `;
        detailTranscript.textContent = t.transcript || '(无转写内容)';
        detailMinutes.textContent = t.minutes || '(无纪要)';
        const knowledge = t.knowledge || [];
        detailKnowledgeCount.textContent = `(${knowledge.length})`;
        knowledge.forEach(k => {
            const div = document.createElement('div');
            div.className = 'entry';
            const title = document.createElement('div');
            title.className = 'title';
            title.textContent = k.title || k.content?.substring(0, 50) || '(无标题)';
            const body = document.createElement('div');
            body.textContent = k.description || k.body || k.content || '';
            div.appendChild(title);
            div.appendChild(body);
            detailKnowledge.appendChild(div);
        });
    } catch (e) {
        detailTitle.textContent = '加载失败';
        detailMeta.textContent = e.message;
    }
}

// ── Recording ──────────────────────────────────────────────
let recording = false;
let audioStream = null;
let mediaRecorder = null;
let meetingId = null;
let chunkNum = 0;
let startTime = 0;
let timerInterval = null;
let chunkTimer = null;
let sseSource = null;
let knowledgeList = [];
let pendingChunks = [];

const CHUNK_MS = 10000;

function formatTimer(ms) {
    const s = Math.floor(ms / 1000);
    return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
}

function connectSSE() {
    sseSource = new EventSource('/api/stream');
    sseSource.addEventListener('transcript', (e) => {
        const data = JSON.parse(e.data);
        const div = document.createElement('div');
        div.className = 'entry';
        div.textContent = `[${data.timestamp}] ${data.text}`;
        transcriptEl.appendChild(div);
        transcriptEl.scrollTop = transcriptEl.scrollHeight;
    });
    sseSource.addEventListener('minutes', (e) => {
        const data = JSON.parse(e.data);
        minutesEl.textContent = data.minutes;
    });
    sseSource.addEventListener('knowledge', (e) => {
        const data = JSON.parse(e.data);
        data.concepts.forEach(c => {
            knowledgeList.push(c);
            const div = document.createElement('div');
            div.className = 'entry';
            const title = document.createElement('div');
            title.className = 'title';
            title.textContent = c.title;
            const body = document.createElement('div');
            body.textContent = c.body || '';
            div.appendChild(title);
            div.appendChild(body);
            knowledgeEl.appendChild(div);
        });
        knowledgeCount.textContent = `(${knowledgeList.length})`;
    });
    sseSource.addEventListener('status', (e) => {
        const data = JSON.parse(e.data);
        chunkCount.textContent = `chunks: ${data.chunks}`;
    });
}

function startMediaRecorder() {
    if (!audioStream || !recording) return;
    mediaRecorder = new MediaRecorder(audioStream, { mimeType: 'audio/webm' });
    const chunks = [];
    mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunks.push(e.data);
    };
    mediaRecorder.onstop = () => {
        if (chunks.length > 0) {
            const blob = new Blob(chunks, { type: 'audio/webm' });
            pendingChunks.push(blob);
        }
        if (recording) {
            startMediaRecorder();
        }
    };
    mediaRecorder.start();
    setTimeout(() => {
        if (mediaRecorder && mediaRecorder.state === 'recording') {
            mediaRecorder.stop();
        }
    }, CHUNK_MS);
}

async function sendPendingChunks() {
    while (pendingChunks.length > 0) {
        const blob = pendingChunks.shift();
        chunkNum++;
        try {
            await fetch(`/api/chunk?meeting_id=${meetingId}`, {
                method: 'POST',
                body: blob,
            });
        } catch (e) {
            console.error('chunk send failed:', e);
        }
    }
}

async function startRecording() {
    const title = document.getElementById('meeting-title').value;
    const participants = document.getElementById('participants').value;

    const resp = await fetch('/api/start', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({title, participants}),
    });
    const data = await resp.json();
    meetingId = data.meeting_id;

    audioStream = await navigator.mediaDevices.getUserMedia({audio: true});

    recording = true;
    recordBtn.classList.add('recording');
    recordBtn.textContent = '⏹ 停止';
    statusText.textContent = '状态: 录音中';
    startTime = Date.now();
    chunkNum = 0;
    pendingChunks = [];
    knowledgeList = [];
    transcriptEl.innerHTML = '';
    minutesEl.innerHTML = '';
    knowledgeEl.innerHTML = '';
    knowledgeCount.textContent = '(0)';

    timerInterval = setInterval(() => {
        timerEl.textContent = formatTimer(Date.now() - startTime);
    }, 1000);

    connectSSE();
    startMediaRecorder();

    chunkTimer = setInterval(sendPendingChunks, 2000);
}

async function stopRecording() {
    recording = false;
    clearInterval(timerInterval);
    clearInterval(chunkTimer);

    if (mediaRecorder && mediaRecorder.state === 'recording') {
        mediaRecorder.stop();
    }

    await new Promise(r => setTimeout(r, 1500));
    await sendPendingChunks();

    if (audioStream) audioStream.getTracks().forEach(t => t.stop());
    if (sseSource) sseSource.close();

    recordBtn.classList.remove('recording');
    recordBtn.textContent = '● 录音';
    statusText.textContent = '状态: 处理中...';

    const resp = await fetch('/api/stop', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({meeting_id: meetingId}),
    });
    const data = await resp.json();
    statusText.textContent = `状态: 已结束 (时长 ${data.duration}s, ${data.chunks} chunks)`;

    setTimeout(() => {
        loadTaskList();
        showView(galleryView);
    }, 2000);
}

// ── Event listeners ────────────────────────────────────────
newMeetingBtn.addEventListener('click', () => {
    showView(recordView);
});

recordBtn.addEventListener('click', () => {
    if (recording) stopRecording();
    else startRecording();
});

homeBtn.addEventListener('click', () => {
    loadTaskList();
    showView(galleryView);
});

detailBackBtn.addEventListener('click', () => {
    loadTaskList();
    showView(galleryView);
});

searchBtn.addEventListener('click', () => {
    showView(searchView);
});

backBtn.addEventListener('click', () => {
    loadTaskList();
    showView(galleryView);
});

doSearchBtn.addEventListener('click', async () => {
    const query = searchQuery.value.trim();
    if (!query) return;
    searchResults.innerHTML = '搜索中...';
    const resp = await fetch(`/api/search?query=${encodeURIComponent(query)}&top_k=10`);
    const data = await resp.json();
    const hits = data.hits || [];
    if (hits.length === 0) {
        searchResults.innerHTML = '<p>无结果</p>';
        return;
    }
    searchResults.innerHTML = `<p>结果 (${hits.length} 条):</p>`;
    hits.forEach(h => {
        const div = document.createElement('div');
        div.className = 'result-item';
        const title = document.createElement('div');
        title.className = 'title';
        title.textContent = h.title || h.content?.substring(0, 50) || '(无标题)';
        const score = document.createElement('div');
        score.className = 'score';
        score.textContent = `score: ${h._distance ?? '?'}`;
        const body = document.createElement('div');
        body.className = 'body';
        body.textContent = h.description || h.content || h.body || '';
        div.appendChild(title);
        div.appendChild(score);
        div.appendChild(body);
        searchResults.appendChild(div);
    });
});

searchQuery.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') doSearchBtn.click();
});

// ── Init: load task gallery ────────────────────────────────
loadTaskList();
