// ========================================
// グローバル変数宣言
// ========================================
let allKnowledgeData = [];
let allSeminarData = [];
let subtitleData = [];
let currentNaturalBg = '01';

// ========================================
// ユーティリティ
// ========================================
function getSecureUrl(url) {
    if (!url) return url;
    if (url.startsWith('http://')) {
        return url.replace('http://', 'https://');
    }
    return url;
}

function getSmartPdfUrl(url) {
    if (!url) return url;
    url = getSecureUrl(url); 
    const isAndroid = /Android/i.test(navigator.userAgent);
    if (isAndroid && url.toLowerCase().includes('.pdf')) {
        let absoluteUrl = url;
        if (!absoluteUrl.startsWith('http')) {
            absoluteUrl = window.location.origin + (url.startsWith('/') ? '' : '/') + url;
        }
        return `https://docs.google.com/viewer?url=${encodeURIComponent(absoluteUrl)}`;
    }
    return url;
}

// ========================================
// 画面遷移管理 (安全版)
// ========================================
const screens = { 
    launcher: document.getElementById('launcherScreen'), 
    search: document.getElementById('searchScreen'),
    seminarSelect: document.getElementById('seminarSelectScreen'),
    seminarPlayer: document.getElementById('seminarPlayerScreen'),
    materialPlayer: document.getElementById('materialPlayerScreen')
};
const launcherWrapper = document.getElementById('launcherWrapper');
const chatContainer = document.getElementById('chatContainer');

function navigateTo(target) {
    console.log("Navigating to:", target);
    if(launcherWrapper) launcherWrapper.style.display = 'block';
    if(chatContainer) chatContainer.style.display = 'none';
    
    Object.values(screens).forEach(screen => {
        if(screen) screen.style.display = 'none';
    });
    
    if(screens[target]) {
        screens[target].style.display = 'flex';
    } else {
        console.warn("Target screen not found:", target);
    }
}

// ========================================
// ボタンイベント
// ========================================
const goToChatButton = document.getElementById('goToChatButton');
if (goToChatButton) {
    goToChatButton.addEventListener('click', () => {
        if(launcherWrapper) launcherWrapper.style.display = 'none';
        if(chatContainer) chatContainer.style.display = 'flex';
    });
}

const goToSearchButton = document.getElementById('goToSearchButton');
if(goToSearchButton) {
    goToSearchButton.addEventListener('click', () => {
        navigateTo('search');
        fetchKnowledgeData();
    });
}

const goToSeminarButton = document.getElementById('goToSeminarButton');
if(goToSeminarButton) {
    goToSeminarButton.addEventListener('click', () => {
        navigateTo('seminarSelect');
        fetchSeminarList();
    });
}

const backBtns = {
    'backFromSearch': 'launcher',
    'backFromSeminarSelect': 'launcher'
};
for (const [id, target] of Object.entries(backBtns)) {
    const btn = document.getElementById(id);
    if(btn) btn.addEventListener('click', () => navigateTo(target));
}

const backFromPlayer = document.getElementById('backFromPlayer');
if(backFromPlayer) {
    backFromPlayer.addEventListener('click', () => {
        const seminarAudio = document.getElementById('seminar-audio');
        if(seminarAudio) seminarAudio.pause();
        navigateTo('seminarSelect');
    });
}

const backFromMaterialPlayer = document.getElementById('backFromMaterialPlayer');
if(backFromMaterialPlayer) {
    backFromMaterialPlayer.addEventListener('click', () => {
        const materialAudio = document.getElementById('material-audio');
        if(materialAudio) materialAudio.pause();
        navigateTo('search');
    });
}

const backToLauncherButton = document.getElementById('backToLauncherButton');
if(backToLauncherButton) {
    backToLauncherButton.addEventListener('click', async () => {
        if (typeof stopS2st === 'function') stopS2st();
        navigateTo('launcher');
    });
}

// ========================================
// テーマ設定
// ========================================
const body = document.body;
const settingsButton = document.getElementById('settingsButton');
const settingsModal = document.getElementById('settingsModal');
const themePreviews = document.querySelectorAll('.theme-preview');
const setLightThemeBtn = document.getElementById('setLightTheme');
const userLogoutBtn = document.getElementById('userLogoutBtn');

function applyTheme(themeName) {
    body.className = '';
    body.classList.add(themeName);
    if (themeName === 'natural-theme' || themeName === 'gold-theme') {
        body.style.backgroundImage = `url('/static/images/background-${currentNaturalBg}.jpg')`;
    } else {
        body.style.backgroundImage = '';
    }
    updateSelectedPreview();
    localStorage.setItem('appTheme', themeName);
    localStorage.setItem('appBgId', currentNaturalBg);
}

function updateSelectedPreview() {
    const isImageTheme = body.classList.contains('natural-theme') || body.classList.contains('gold-theme');
    themePreviews.forEach(p => {
        p.classList.toggle('selected', p.dataset.bg === currentNaturalBg && isImageTheme);
    });
}

if(settingsButton) {
    settingsButton.addEventListener('click', () => {
        updateSelectedPreview();
        if(settingsModal) settingsModal.style.display = 'flex';
    });
}

if(settingsModal) {
    settingsModal.addEventListener('click', e => {
        if (e.target === settingsModal) settingsModal.style.display = 'none';
    });
}

themePreviews.forEach(preview => {
    preview.addEventListener('click', () => {
        currentNaturalBg = preview.dataset.bg;
        const bgNumber = parseInt(currentNaturalBg, 10);
        if (bgNumber <= 6) applyTheme('gold-theme'); 
        else applyTheme('natural-theme'); 
        if(settingsModal) settingsModal.style.display = 'none';
    });
});

if(setLightThemeBtn) {
    setLightThemeBtn.addEventListener('click', () => {
        applyTheme('light-theme');
        if(settingsModal) settingsModal.style.display = 'none';
    });
}

if(userLogoutBtn) {
    userLogoutBtn.addEventListener('click', () => {
        window.location.href = '/logout';
    });
}

// ========================================
// セミナー・資料リスト
// ========================================
const seminarListContainer = document.getElementById('seminarList');
const seminarAudio = document.getElementById('seminar-audio');
const seminarSearchInput = document.getElementById('seminarSearchInput');

async function fetchSeminarList() {
    try {
        const response = await fetch('/get_seminar_list');
        allSeminarData = await response.json();
        renderSeminarList(allSeminarData);
    } catch (error) {
        if(seminarListContainer) seminarListContainer.innerHTML = '<p class="no-results">読み込みエラー</p>';
    }
}

function renderSeminarList(data) {
    if(!seminarListContainer) return;
    if (data.length === 0) {
        seminarListContainer.innerHTML = '<p class="no-results">該当なし</p>';
        return;
    }
    seminarListContainer.innerHTML = data.map(item => `
        <div class="knowledge-card">
            <h3 class="card-topic-title">${item.topic_title}</h3>
            <button class="card-button play" onclick="startSeminar(${item.id})">
                <i class="fas fa-play-circle"></i> 受講する
            </button>
        </div>
    `).join('');
}

if(seminarSearchInput) {
    seminarSearchInput.addEventListener('input', (e) => {
        const keyword = e.target.value.toLowerCase().trim();
        const filtered = allSeminarData.filter(i => i.topic_title.toLowerCase().includes(keyword));
        renderSeminarList(filtered);
    });
}

const knowledgeListContainer = document.getElementById('knowledgeList');
const searchInput = document.getElementById('searchInput');

async function fetchKnowledgeData() {
    try {
        const response = await fetch('/get_knowledge_data');
        allKnowledgeData = await response.json();
        renderKnowledgeList(allKnowledgeData);
    } catch (error) {
        if(knowledgeListContainer) knowledgeListContainer.innerHTML = 'エラー';
    }
}

function renderKnowledgeList(data) {
    if(!knowledgeListContainer) return;
    knowledgeListContainer.innerHTML = data.map(item => `
        <div class="knowledge-card">
            <h3 class="card-topic-title">${item.topic_title}</h3>
            <div class="card-links">
                <button class="card-button video ${item.has_audio?'':'disabled'}" onclick="playMaterialAudio('${getSecureUrl(item.lecture_audio_url)}', '${item.topic_title}')">音声</button>
                <a href="${getSmartPdfUrl(item.pdf_file_url)}" target="_blank" class="card-button pdf ${item.has_pdf?'':'disabled'}">資料</a>
            </div>
        </div>
    `).join('');
}

if(searchInput) {
    searchInput.addEventListener('input', (e) => {
        const keyword = e.target.value.toLowerCase().trim();
        const filtered = allKnowledgeData.filter(i => i.topic_title.toLowerCase().includes(keyword));
        renderKnowledgeList(filtered);
    });
}

// ========================================
// S2ST (Live API) ロジック
// ========================================
const s2stBtn = document.getElementById('s2stStartBtn');
const s2stStatus = document.getElementById('s2stStatus');
const orb = document.getElementById('orb');
const transcript = document.getElementById('s2stTranscript');
const voiceSelect = document.getElementById('voiceSelect');

let micCtx = null;
let workletNode = null;
let sourceNode = null;
let micStream = null;
let playCtx = null;
let nextStartAt = 0;
let lastSrc = null;
let ws = null;
let isLiveRunning = false;

function setS2stStatus(t, c='') { if(s2stStatus) { s2stStatus.textContent=t; s2stStatus.className='s2st-status '+c; } }
function setOrb(m) { if(orb) orb.className='orb '+(m||''); }

function addTranscriptLine(who, text) {
    if(!transcript) return;
    const last = transcript.lastElementChild;
    if (last && last.classList.contains(who)) {
        last.querySelector('.msg').textContent += text;
    } else {
        const d = document.createElement('div');
        d.className = 'line '+who;
        d.innerHTML = `<span class="who">${who==='user'?'YOU':'AI'}</span><span class="msg">${text}</span>`;
        transcript.appendChild(d);
    }
    transcript.scrollTop = transcript.scrollHeight;
}

function scheduleLiveAudio(pcmBytes) {
    if (!isLiveRunning) return;
    if (!playCtx || playCtx.state === 'closed') {
        const AudioContext = window.AudioContext || window.webkitAudioContext;
        playCtx = new AudioContext({ sampleRate: 24000 });
        nextStartAt = 0;
    }
    if (playCtx.state === 'suspended') playCtx.resume();
    const int16 = new Int16Array(pcmBytes);
    const float32 = new Float32Array(int16.length);
    for (let i = 0; i < int16.length; i++) float32[i] = int16[i] / 32768;
    const buf = playCtx.createBuffer(1, float32.length, 24000);
    buf.copyToChannel(float32, 0);
    const src = playCtx.createBufferSource();
    src.buffer = buf;
    src.connect(playCtx.destination);
    const startAt = Math.max(nextStartAt, playCtx.currentTime);
    src.start(startAt);
    nextStartAt = startAt + buf.duration;
    if (lastSrc) lastSrc.onended = null;
    lastSrc = src;
    setOrb('speaking');
    setS2stStatus('AI が回答中...', 'ai');
    src.onended = () => {
        if (src === lastSrc && isLiveRunning) { setOrb('listening'); setS2stStatus('聞き取り中...', 'active'); }
    };
}

async function startS2st() {
    try {
        const username = document.querySelector('meta[name="app-username"]')?.content || 'guest';
        const sessionId = document.querySelector('meta[name="app-session-id"]')?.content || Date.now();
        const voice = voiceSelect ? voiceSelect.value : 'Aoede';
        if(voiceSelect) voiceSelect.disabled = true;

        const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${location.host}/ws/chat?username=${encodeURIComponent(username)}&session_id=${encodeURIComponent(sessionId)}&voice=${encodeURIComponent(voice)}`;
        
        ws = new WebSocket(wsUrl);
        ws.binaryType = 'arraybuffer';
        ws.onmessage = (e) => {
            if (e.data instanceof ArrayBuffer) scheduleLiveAudio(e.data);
            else {
                const s = e.data;
                if (s.startsWith('USER:')) addTranscriptLine('user', s.slice(5));
                else if (s.startsWith('AI:')) addTranscriptLine('ai', s.slice(3));
            }
        };
        ws.onerror = () => stopS2st();
        ws.onclose = () => { if (isLiveRunning) stopS2st(); };

        micStream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, sampleRate: 16000, echoCancellation: true, noiseSuppression: true } });
        const AudioContext = window.AudioContext || window.webkitAudioContext;
        micCtx = new AudioContext({ sampleRate: 16000 });
        const workletCode = document.getElementById('worklet-src').textContent;
        const blobUrl = URL.createObjectURL(new Blob([workletCode], { type: 'application/javascript' }));
        await micCtx.audioWorklet.addModule(blobUrl);
        workletNode = new AudioWorkletNode(micCtx, 'pcm-processor');
        workletNode.port.onmessage = (e) => { if (ws && ws.readyState === WebSocket.OPEN) ws.send(e.data); };
        sourceNode = micCtx.createMediaStreamSource(micStream);
        sourceNode.connect(workletNode);
       isLiveRunning = true;
       if(s2stBtn) {
           s2stBtn.textContent = '会話を終了'; // 文言変更
           s2stBtn.classList.add('stop');
       }
       setOrb('listening');
       setS2stStatus('聞き取り中...', 'active')

    } catch(err) { stopS2st(); }
}

function stopS2st() {
    isLiveRunning = false;
    if(workletNode) workletNode.disconnect();
    if(sourceNode) sourceNode.disconnect();
    if(micStream) micStream.getTracks().forEach(t => t.stop());
    if(micCtx) micCtx.close();
    if(playCtx) playCtx.close();
    if(ws) ws.close();
    if(s2stBtn) {
        s2stBtn.textContent = '会話を開始'; // 文言変更
        s2stBtn.classList.remove('stop');
    }
    if(voiceSelect) voiceSelect.disabled = false;
    setOrb('');
    setS2stStatus('待機中');
}

if(s2stBtn) s2stBtn.addEventListener('click', () => isLiveRunning ? stopS2st() : startS2st());

// ========================================
// 初期化
// ========================================
(function init() {
    const savedTheme = localStorage.getItem('appTheme') || 'gold-theme';
    const savedBg = localStorage.getItem('appBgId') || '01';
    currentNaturalBg = savedBg;
    applyTheme(savedTheme);
    navigateTo('launcher');
})();