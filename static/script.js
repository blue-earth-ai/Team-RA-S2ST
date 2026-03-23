// ========================================
// グローバル変数宣言
// ========================================
let allKnowledgeData = [];
let allSeminarData = [];
let subtitleData = []; // 字幕データ保持用
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

function formatTime(seconds) {
    if (!seconds || isNaN(seconds)) return '0:00';
    const min = Math.floor(seconds / 60);
    const sec = Math.floor(seconds % 60);
    return `${min}:${sec < 10 ? '0' : ''}${sec}`;
}

// ========================================
// 画面遷移管理
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
    if(launcherWrapper) launcherWrapper.style.display = 'block';
    if(chatContainer) chatContainer.style.display = 'none';
    
    Object.values(screens).forEach(screen => {
        if(screen) screen.style.display = 'none';
    });
    
    if(screens[target]) {
        screens[target].style.display = 'flex';
    }
}

// ========================================
// ボタンイベント
// ========================================
if (document.getElementById('goToChatButton')) {
    document.getElementById('goToChatButton').addEventListener('click', () => {
        if(launcherWrapper) launcherWrapper.style.display = 'none';
        if(chatContainer) chatContainer.style.display = 'flex';
    });
}

if(document.getElementById('goToSearchButton')) {
    document.getElementById('goToSearchButton').addEventListener('click', () => {
        navigateTo('search');
        fetchKnowledgeData();
    });
}

if(document.getElementById('goToSeminarButton')) {
    document.getElementById('goToSeminarButton').addEventListener('click', () => {
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

if(document.getElementById('backFromPlayer')) {
    document.getElementById('backFromPlayer').addEventListener('click', () => {
        const seminarAudio = document.getElementById('seminar-audio');
        if(seminarAudio) seminarAudio.pause();
        navigateTo('seminarSelect');
    });
}

if(document.getElementById('backFromMaterialPlayer')) {
    document.getElementById('backFromMaterialPlayer').addEventListener('click', () => {
        const materialAudio = document.getElementById('material-audio');
        if(materialAudio) materialAudio.pause();
        navigateTo('search');
    });
}

if(document.getElementById('backToLauncherButton')) {
    document.getElementById('backToLauncherButton').addEventListener('click', () => {
        if (typeof stopS2st === 'function') stopS2st();
        navigateTo('launcher');
    });
}

// ========================================
// テーマ設定
// ========================================
const body = document.body;
const themePreviews = document.querySelectorAll('.theme-preview');

function applyTheme(themeName) {
    body.className = '';
    body.classList.add(themeName);
    if (themeName === 'natural-theme' || themeName === 'gold-theme') {
        body.style.backgroundImage = `url('/static/images/background-${currentNaturalBg}.jpg')`;
    } else {
        body.style.backgroundImage = '';
    }
    localStorage.setItem('appTheme', themeName);
    localStorage.setItem('appBgId', currentNaturalBg);
}

if(document.getElementById('settingsButton')) {
    document.getElementById('settingsButton').addEventListener('click', () => {
        const modal = document.getElementById('settingsModal');
        if(modal) modal.style.display = 'flex';
    });
}

themePreviews.forEach(preview => {
    preview.addEventListener('click', () => {
        currentNaturalBg = preview.dataset.bg;
        const bgNumber = parseInt(currentNaturalBg, 10);
        if (bgNumber <= 6) applyTheme('gold-theme'); 
        else applyTheme('natural-theme'); 
        const modal = document.getElementById('settingsModal');
        if(modal) modal.style.display = 'none';
    });
});

if(document.getElementById('userLogoutBtn')) {
    document.getElementById('userLogoutBtn').addEventListener('click', () => {
        window.location.href = '/logout';
    });
}

// ========================================
// AIセミナー機能 (リスト表示)
// ========================================
const seminarListContainer = document.getElementById('seminarList');

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
        seminarListContainer.innerHTML = '<p class="no-results">セミナーが見つかりません。</p>';
        return;
    }
    
    seminarListContainer.innerHTML = data.map(item => {
        let textbookInfo = '';
        if (item.textbook_path) {
            let displayName = item.seminar_doc_name ? item.seminar_doc_name.replace(/\.pdf$/i, "") : "関連資料";
            const pageInfo = item.textbook_page ? `（${item.textbook_page}ページ）` : '';
            const displayText = `対象テキスト：<br>${displayName}${pageInfo}`;
            let hrefPath = getSmartPdfUrl(item.textbook_path);

            textbookInfo = `
                <div class="seminar-textbook-info">
                    <a href="${hrefPath}" target="_blank" class="seminar-textbook-link">
                        <i class="fas fa-book-open"></i> ${displayText}
                    </a>
                </div>
            `;
        }
        
        return `
            <div class="knowledge-card">
                <div class="seminar-header">
                    <h3 class="card-topic-title">${item.topic_title}</h3>
                    ${textbookInfo}
                </div>
                <button class="card-button play" onclick="startSeminar(${item.id})">
                    <i class="fas fa-play-circle"></i> 受講する
                </button>
            </div>
        `;
    }).join('');
}

// ========================================
// 資料検索ロジック
// ========================================
const knowledgeListContainer = document.getElementById('knowledgeList');

async function fetchKnowledgeData() {
    try {
        const response = await fetch('/get_knowledge_data');
        allKnowledgeData = await response.json();
        renderKnowledgeList(allKnowledgeData);
    } catch (error) {
        if(knowledgeListContainer) knowledgeListContainer.innerHTML = '読み込みエラー';
    }
}

function renderKnowledgeList(data) {
    if(!knowledgeListContainer) return;
    if (data.length === 0) {
        knowledgeListContainer.innerHTML = '<p class="no-results">該当資料なし</p>';
        return;
    }
    knowledgeListContainer.innerHTML = data.map(item => {
        const safeAudioUrl = item.lecture_audio_url ? getSecureUrl(item.lecture_audio_url).replace(/'/g, "\\'") : '';
        const safeTitle = item.topic_title ? item.topic_title.replace(/'/g, "\\'") : '';

        const audioBtn = item.has_audio 
            ? `<button class="card-button video" onclick="playMaterialAudio('${safeAudioUrl}', '${safeTitle}')"><i class="fas fa-volume-up"></i> 音声</button>`
            : `<button class="card-button video disabled" disabled><i class="fas fa-volume-up"></i> 音声</button>`;
        
        const pdfBtn = item.has_pdf 
            ? `<a href="${getSmartPdfUrl(item.pdf_file_url)}" target="_blank" class="card-button pdf"><i class="fas fa-file-pdf"></i> 資料</a>`
            : `<button class="card-button pdf disabled" disabled><i class="fas fa-file-pdf"></i> 資料</button>`;
        
        return `
            <div class="knowledge-card">
                <h3 class="card-topic-title">${item.topic_title}</h3>
                <div class="card-links">
                    ${audioBtn}
                    ${pdfBtn}
                </div>
            </div>
        `;
    }).join('');
}

window.playMaterialAudio = (url, title) => {
    const materialAudio = document.getElementById('material-audio');
    const playerTitle = document.getElementById('materialPlayerTitle');
    if (url && materialAudio) {
        if(playerTitle) playerTitle.innerText = title;
        materialAudio.src = url;
        materialAudio.load();
        navigateTo('materialPlayer');
        setTimeout(() => { materialAudio.play().catch(()=>{}); }, 150);
    }
};

// ========================================
// AIセミナー再生・字幕・ビジュアライザー (修復版)
// ========================================
const seminarAudio = document.getElementById('seminar-audio');
const subtitleText = document.getElementById('subtitleText');
const visualizerContainer = document.querySelector('.visualizer-container');
const seminarPlayPauseBtn = document.getElementById('seminarPlayPauseBtn');
const seminarProgressFill = document.getElementById('seminarProgressFill');
const seminarCurrentTime = document.getElementById('seminarCurrentTime');
const seminarDuration = document.getElementById('seminarDuration');

// 字幕生成ロジック
function generateSubtitles(fullText, duration) {
    if (!fullText) return [];
    // 句読点や改行で分割
    const rawSentences = fullText.split(/([。！？\n]+)/).filter(Boolean);
    let sentences = [];
    for (let i = 0; i < rawSentences.length; i += 2) {
        let text = rawSentences[i];
        if (i + 1 < rawSentences.length) text += rawSentences[i + 1];
        if (text.trim()) sentences.push(text.trim());
    }
    const totalLength = sentences.join('').length;
    let currentTime = 0;
    const subtitles = [];
    sentences.forEach(sentence => {
        const sentenceDuration = (sentence.length / totalLength) * duration;
        subtitles.push({
            text: sentence,
            start: currentTime,
            end: currentTime + sentenceDuration
        });
        currentTime += sentenceDuration;
    });
    return subtitles;
}

// ビジュアライザー制御
function toggleVisualizer(isPlaying) {
    if(!visualizerContainer) return;
    if (isPlaying) visualizerContainer.classList.add('playing');
    else visualizerContainer.classList.remove('playing');
}

if(seminarAudio) {
    // メタデータ読み込み時
    seminarAudio.addEventListener('loadedmetadata', () => {
        const text = seminarAudio.dataset.fullText;
        const duration = seminarAudio.duration;
        if (text && duration) {
            subtitleData = generateSubtitles(text, duration);
            if(subtitleText && subtitleData.length > 0) subtitleText.innerText = subtitleData[0].text;
        }
        if(seminarDuration) seminarDuration.innerText = formatTime(duration);
    });

    // 再生中（時間更新時）
    seminarAudio.addEventListener('timeupdate', () => {
        if(seminarAudio.duration) {
            const current = seminarAudio.currentTime;
            // 進捗バー更新
            const percent = (current / seminarAudio.duration) * 100;
            if(seminarProgressFill) seminarProgressFill.style.width = percent + '%';
            if(seminarCurrentTime) seminarCurrentTime.innerText = formatTime(current);
            
            // 字幕更新 (0.9を掛けて少し早めに出す調整)
            if (subtitleData.length > 0 && subtitleText) {
                const currentSubtitle = subtitleData.find(s => current >= s.start && current < s.end);
                if (currentSubtitle) {
                    if (subtitleText.innerText !== currentSubtitle.text) subtitleText.innerText = currentSubtitle.text;
                }
            }
        }
    });

    seminarAudio.addEventListener('play', () => {
        if(seminarPlayPauseBtn) seminarPlayPauseBtn.innerHTML = '<i class="fas fa-pause"></i>';
        toggleVisualizer(true);
    });

    seminarAudio.addEventListener('pause', () => {
        if(seminarPlayPauseBtn) seminarPlayPauseBtn.innerHTML = '<i class="fas fa-play"></i>';
        toggleVisualizer(false);
    });

    seminarAudio.addEventListener('ended', () => {
        if(seminarPlayPauseBtn) seminarPlayPauseBtn.innerHTML = '<i class="fas fa-play"></i>';
        toggleVisualizer(false);
    });
}

// 再生・一時停止ボタン
if(seminarPlayPauseBtn) {
    seminarPlayPauseBtn.addEventListener('click', () => {
        if (seminarAudio.paused) seminarAudio.play();
        else seminarAudio.pause();
    });
}

// プログレスバークリックでシーク
const seminarProgressContainer = document.getElementById('seminarProgressContainer');
if(seminarProgressContainer) {
    seminarProgressContainer.addEventListener('click', (e) => {
        const width = seminarProgressContainer.clientWidth;
        const clickX = e.offsetX;
        const duration = seminarAudio.duration;
        if(seminarAudio && duration) seminarAudio.currentTime = (clickX / width) * duration;
    });
}

// 再生速度変更
document.querySelectorAll('.sem-speed-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.sem-speed-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        if(seminarAudio) seminarAudio.playbackRate = parseFloat(btn.dataset.speed);
    });
});

// セミナー開始処理
window.startSeminar = async (id) => {
    const loadingOverlay = document.getElementById('loadingOverlay');
    if(loadingOverlay) loadingOverlay.style.display = 'flex';
    
    try {
        const response = await fetch('/start_seminar', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ id: id })
        });
        const data = await response.json();
        if (data.audio_url) {
            const playerTitle = document.getElementById('playerTitle');
            if(playerTitle) playerTitle.innerText = data.topic_title;
            const transcriptEl = document.getElementById('playerTranscript');
            if (transcriptEl) transcriptEl.innerText = data.transcript_text;
            
            if(seminarAudio) {
                // 字幕用テキストをデータ属性に保持
                seminarAudio.dataset.fullText = data.transcript_text;
                seminarAudio.src = data.audio_url;
                seminarAudio.load();
                navigateTo('seminarPlayer');
                setTimeout(() => { seminarAudio.play().catch(()=>{}); }, 300);
            }
        }
    } catch (error) {
        alert('エラーが発生しました。');
    } finally {
        if(loadingOverlay) loadingOverlay.style.display = 'none';
    }
};

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
        if(s2stBtn) { s2stBtn.textContent = '会話を終了'; s2stBtn.classList.add('stop'); }
        setOrb('listening');
        setS2stStatus('聞き取り中...', 'active');
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
    if(s2stBtn) { s2stBtn.textContent = '会話を開始'; s2stBtn.classList.remove('stop'); }
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