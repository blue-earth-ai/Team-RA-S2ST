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
    if(screens[target]) screens[target].style.display = 'flex';
}

// ========================================
// ボタンイベント (安全策追加)
// ========================================
const goToChatButton = document.getElementById('goToChatButton');
if (goToChatButton) {
    goToChatButton.addEventListener('click', () => {
        if(launcherWrapper) launcherWrapper.style.display = 'none';
        if(chatContainer) chatContainer.style.display = 'flex';
        
        const existingMessages = document.querySelectorAll('#chat-window .message');
        if (existingMessages.length === 0) {
            setTimeout(async () => {
                try {
                    const response = await fetch('/get_greeting');
                    const data = await response.json();
                    if (data.text && data.audio_url) {
                        addChatMessage('ai', data.text);
                        playAudio(data.audio_url);
                    }
                } catch(e) {}
            }, 500);
        }
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

// 戻るボタン系
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
        navigateTo('launcher');
        const chatWin = document.getElementById('chat-window');
        if(chatWin) chatWin.innerHTML = ''; 
        try { await fetch('/reset_session', { method: 'POST' }); } catch (e) {}
    });
}

// ========================================
// テーマ設定 & ログアウト
// ========================================
const body = document.body;
const settingsButton = document.getElementById('settingsButton');
const settingsModal = document.getElementById('settingsModal');
const themePreviews = document.querySelectorAll('.theme-preview');
const setLightThemeBtn = document.getElementById('setLightTheme');
const userLogoutBtn = document.getElementById('userLogoutBtn');

let currentNaturalBg = '01';

function applyTheme(themeName) {
    body.className = '';
    body.classList.add(themeName);
    if (themeName === 'natural-theme' || themeName === 'gold-theme') {
        body.style.backgroundImage = `url('/static/images/background-${currentNaturalBg}.jpg')`;
    } else {
        body.style.backgroundImage = '';
    }
    updateSelectedPreview();
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
        settingsModal.style.display = 'flex';
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
        if (bgNumber <= 6) { 
            applyTheme('gold-theme'); 
        } else { 
            applyTheme('natural-theme'); 
        }
        settingsModal.style.display = 'none';
    });
});

if(setLightThemeBtn) {
    setLightThemeBtn.addEventListener('click', () => {
        applyTheme('light-theme');
        settingsModal.style.display = 'none';
    });
}

// ログアウト処理（確認ダイアログなしで即実行）
if(userLogoutBtn) {
    userLogoutBtn.addEventListener('click', () => {
        window.location.href = '/logout';
    });
}

applyTheme('gold-theme');
navigateTo('launcher');

// ========================================
// AIセミナー機能
// ========================================
const seminarListContainer = document.getElementById('seminarList');
const loadingOverlay = document.getElementById('loadingOverlay');
const seminarAudio = document.getElementById('seminar-audio');
const playerAvatar = document.getElementById('playerAvatar');
const playerTitle = document.getElementById('playerTitle');

// ID取得
const seminarPlayPauseBtn = document.getElementById('seminarPlayPauseBtn');
const seminarProgressFill = document.getElementById('seminarProgressFill');
const seminarProgressContainer = document.getElementById('seminarProgressContainer');
const seminarCurrentTime = document.getElementById('seminarCurrentTime');
const seminarDuration = document.getElementById('seminarDuration');
const seminarSpeedBtns = document.querySelectorAll('.sem-speed-btn'); 

const visualizerContainer = document.querySelector('.visualizer-container');
const subtitleText = document.getElementById('subtitleText');
const seminarSearchInput = document.getElementById('seminarSearchInput');

let subtitleData = []; 
let allSeminarData = []; 

async function fetchSeminarList() {
    try {
        const response = await fetch('/get_seminar_list');
        const data = await response.json();
        allSeminarData = data;
        renderSeminarList(allSeminarData);
    } catch (error) {
        if(seminarListContainer) seminarListContainer.innerHTML = '<p class="no-results">読み込みに失敗しました。</p>';
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
            let displayName = "";
            if (item.seminar_doc_name) {
                displayName = item.seminar_doc_name.replace(/\.pdf$/i, "");
            } else {
                displayName = item.textbook_path.split('/').pop().replace(/\.[^/.]+$/, "");
            }

            const pageInfo = item.textbook_page ? `（${item.textbook_page}ページ）` : '';
            const displayText = `対象テキスト：<br>${displayName}${pageInfo}`;
            
            let hrefPath = item.textbook_path;
            if (!hrefPath.startsWith('http') && !hrefPath.startsWith('/')) {
                hrefPath = '/' + hrefPath;
            }

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

if(seminarSearchInput) {
    seminarSearchInput.addEventListener('input', (e) => {
        const keyword = e.target.value.toLowerCase().trim();
        const filteredData = allSeminarData.filter(item => 
            item.topic_title.toLowerCase().includes(keyword)
        );
        renderSeminarList(filteredData);
    });
}

window.startSeminar = async (id) => {
    if(loadingOverlay) loadingOverlay.style.display = 'flex';
    const TIMEOUT_MS = 300000; // 300秒(5分)に延長
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), TIMEOUT_MS);

    try {
        const response = await fetch('/start_seminar', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ id: id }),
            signal: controller.signal
        });
        clearTimeout(timeoutId);
        
        if (!response.ok) throw new Error(`Server error: ${response.status}`);

        const data = await response.json();

        if (data.audio_url) {
            if(playerTitle) playerTitle.innerText = data.topic_title;
            let avatarSrc = data.avatar_url || '/static/images/default_avatar.png';
            if (!avatarSrc.startsWith('http') && !avatarSrc.startsWith('/')) avatarSrc = '/' + avatarSrc; 
            if(playerAvatar) playerAvatar.src = avatarSrc;
            
            const transcriptEl = document.getElementById('playerTranscript');
            if (transcriptEl) {
                transcriptEl.innerText = data.transcript_text || 'テキスト情報がありません';
            }
            
            const transcriptText = data.transcript_text || "";
            if(seminarAudio) seminarAudio.dataset.fullText = transcriptText;
            
            if (!transcriptText) {
                if(subtitleText) subtitleText.innerText = "字幕情報がありません";
            } else {
                if(subtitleText) subtitleText.innerText = "読み込み中...";
            }

            if(seminarAudio) {
                seminarAudio.src = data.audio_url;
                seminarAudio.load();
                navigateTo('seminarPlayer');
                
                seminarAudio.play().then(() => {
                    updateSeminarPlayPauseIcon(true);
                    toggleVisualizer(true);
                }).catch(e => console.log("自動再生ブロック:", e));
            }
        } else {
            alert('音声データの取得に失敗しました。');
        }

    } catch (error) {
        if (error.name === 'AbortError') {
            alert('生成に時間がかかっています。通信環境の良い場所で再度お試しください。');
        } else {
            console.error(error);
            alert('エラーが発生しました。しばらく待ってから再度お試しください。');
        }
    } finally {
        if(loadingOverlay) loadingOverlay.style.display = 'none';
        clearTimeout(timeoutId);
    }
};

function updateSeminarPlayPauseIcon(isPlaying) {
    if(seminarPlayPauseBtn) seminarPlayPauseBtn.innerHTML = isPlaying ? '<i class="fas fa-pause"></i>' : '<i class="fas fa-play"></i>';
}

function toggleVisualizer(isPlaying) {
    if(!visualizerContainer) return;
    if (isPlaying) visualizerContainer.classList.add('playing');
    else visualizerContainer.classList.remove('playing');
}

function generateSubtitles(fullText, duration) {
    if (!fullText) return [];
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

// セミナー用のイベントリスナー
if(seminarPlayPauseBtn) {
    seminarPlayPauseBtn.addEventListener('click', () => {
        if (seminarAudio.paused) {
            seminarAudio.play();
            updateSeminarPlayPauseIcon(true);
            toggleVisualizer(true);
        } else {
            seminarAudio.pause();
            updateSeminarPlayPauseIcon(false);
            toggleVisualizer(false);
        }
    });
}

if(seminarAudio) {
    seminarAudio.addEventListener('loadedmetadata', () => {
        // ボタン有効化
        if(seminarPlayPauseBtn) seminarPlayPauseBtn.disabled = false;

        const text = seminarAudio.dataset.fullText;
        const duration = seminarAudio.duration;
        if (text && duration) {
            subtitleData = generateSubtitles(text, duration);
            if(subtitleText && subtitleData.length > 0) subtitleText.innerText = subtitleData[0].text;
        }
        if(seminarDuration) seminarDuration.innerText = formatTime(duration);
        if(seminarProgressFill) seminarProgressFill.style.width = '0%';
    });

    seminarAudio.addEventListener('timeupdate', () => {
        if(seminarAudio.duration) {
            const current = seminarAudio.currentTime;
            const percent = (current / seminarAudio.duration) * 100;
            if(seminarProgressFill) seminarProgressFill.style.width = percent + '%';
            if(seminarCurrentTime) seminarCurrentTime.innerText = formatTime(current);
            
            // 字幕の切り替わりスピード調整 (0.9 = 10%遅延)
            const lookaheadTime = current * 0.9;
            
            if (subtitleData.length > 0 && subtitleText) {
                const currentSubtitle = subtitleData.find(s => lookaheadTime >= s.start && lookaheadTime < s.end);
                if (currentSubtitle) {
                    if (subtitleText.innerText !== currentSubtitle.text) subtitleText.innerText = currentSubtitle.text;
                }
            }
        }
    });

    seminarAudio.addEventListener('ended', () => {
        updateSeminarPlayPauseIcon(false);
        toggleVisualizer(false);
        if(seminarProgressFill) seminarProgressFill.style.width = '0%';
    });
}

if(seminarProgressContainer) {
    seminarProgressContainer.addEventListener('click', (e) => {
        const width = seminarProgressContainer.clientWidth;
        const clickX = e.offsetX;
        const duration = seminarAudio.duration;
        if(seminarAudio) seminarAudio.currentTime = (clickX / width) * duration;
    });
}

// 速度ボタンの制御
seminarSpeedBtns.forEach(btn => {
    btn.addEventListener('click', () => {
        seminarSpeedBtns.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        if(seminarAudio) seminarAudio.playbackRate = parseFloat(btn.dataset.speed);
    });
});

function formatTime(seconds) {
    if (!seconds || isNaN(seconds)) return '0:00';
    const min = Math.floor(seconds / 60);
    const sec = Math.floor(seconds % 60);
    return `${min}:${sec < 10 ? '0' : ''}${sec}`;
}

// ========================================
// 資料検索ロジック
// ========================================
const knowledgeListContainer = document.getElementById('knowledgeList');
const searchInput = document.getElementById('searchInput');

async function fetchKnowledgeData() {
    try {
        const response = await fetch('/get_knowledge_data');
        allKnowledgeData = await response.json();
        renderKnowledgeList(allKnowledgeData);
    } catch (error) {
        if(knowledgeListContainer) knowledgeListContainer.innerHTML = '<p class="no-results">読み込みエラー</p>';
    }
}

function renderKnowledgeList(data) {
    if(!knowledgeListContainer) return;
    
    if (data.length === 0) {
        knowledgeListContainer.innerHTML = '<p class="no-results">該当資料なし</p>';
        return;
    }
    
    knowledgeListContainer.innerHTML = data.map(item => {
        const safeAudioUrl = item.lecture_audio_url ? item.lecture_audio_url.replace(/'/g, "\\'") : '';
        const safeTitle = item.topic_title ? item.topic_title.replace(/'/g, "\\'") : '';

        const audioBtn = item.has_audio 
            ? `<button class="card-button video" onclick="playMaterialAudio('${safeAudioUrl}', '${safeTitle}')">
                   <i class="fas fa-volume-up"></i> 音声
               </button>`
            : `<button class="card-button video disabled" disabled>
                   <i class="fas fa-volume-up"></i> 音声
               </button>`;
        
        const pdfBtn = item.has_pdf 
            ? `<a href="${item.pdf_file_url}" target="_blank" class="card-button pdf">
                   <i class="fas fa-file-pdf"></i> 資料
               </a>`
            : `<button class="card-button pdf disabled" disabled>
                   <i class="fas fa-file-pdf"></i> 資料
               </button>`;
        
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
        navigateTo('materialPlayer');
        materialAudio.play().catch(e => console.log("自動再生エラー:", e));
    }
};

if(searchInput) {
    searchInput.addEventListener('input', (e) => {
        const keyword = e.target.value.toLowerCase().trim();
        const filteredData = allKnowledgeData.filter(item => 
            item.topic_title.toLowerCase().includes(keyword)
        );
        renderKnowledgeList(filteredData);
    });
}

// ========================================
// チャット音声コントロール
// ========================================
(function() {
    const audioPlayer = document.getElementById('audio-player');
    const chatPlayPauseBtn = document.getElementById('chatPlayPauseBtn');
    const chatProgressFill = document.getElementById('chatProgressFill');
    const chatProgressContainer = document.getElementById('chatProgressContainer');
    const chatCurrentTime = document.getElementById('chatCurrentTime');
    const chatDuration = document.getElementById('chatDuration');
    const chatSpeedBtns = document.querySelectorAll('.chat-speed-btn');
    
    if(!audioPlayer || !chatPlayPauseBtn) return;

    function formatTime(seconds) {
        if (!seconds || isNaN(seconds)) return '0:00';
        const min = Math.floor(seconds / 60);
        const sec = Math.floor(seconds % 60);
        return `${min}:${sec < 10 ? '0' : ''}${sec}`;
    }
    
    chatPlayPauseBtn.addEventListener('click', () => {
        if (audioPlayer.paused) {
            audioPlayer.play();
        } else {
            audioPlayer.pause();
        }
    });
    
    audioPlayer.addEventListener('loadedmetadata', () => {
        chatPlayPauseBtn.disabled = false;
        if(chatDuration) chatDuration.textContent = formatTime(audioPlayer.duration);
        if(chatProgressFill) chatProgressFill.style.width = '0%';
    });
    
    audioPlayer.addEventListener('timeupdate', () => {
        if (audioPlayer.duration) {
            const percent = (audioPlayer.currentTime / audioPlayer.duration) * 100;
            if(chatProgressFill) chatProgressFill.style.width = percent + '%';
            if(chatCurrentTime) chatCurrentTime.textContent = formatTime(audioPlayer.currentTime);
        }
    });
    
    audioPlayer.addEventListener('play', () => {
        chatPlayPauseBtn.innerHTML = '<i class="fas fa-pause"></i>';
    });
    
    audioPlayer.addEventListener('pause', () => {
        chatPlayPauseBtn.innerHTML = '<i class="fas fa-play"></i>';
    });
    
    audioPlayer.addEventListener('ended', () => {
        chatPlayPauseBtn.innerHTML = '<i class="fas fa-play"></i>';
        if(chatProgressFill) chatProgressFill.style.width = '0%';
        chatPlayPauseBtn.disabled = true;
    });
    
    if(chatProgressContainer) {
        chatProgressContainer.addEventListener('click', (e) => {
            if (audioPlayer.duration) {
                const rect = chatProgressContainer.getBoundingClientRect();
                const clickX = e.clientX - rect.left;
                const width = rect.width;
                audioPlayer.currentTime = (clickX / width) * audioPlayer.duration;
            }
        });
    }
    
    chatSpeedBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            chatSpeedBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            audioPlayer.playbackRate = parseFloat(btn.dataset.speed);
        });
    });
})();

// ========================================
// チャット関連 (Router/地球儀/フィードバック対応)
// ========================================
const audioPlayer = document.getElementById('audio-player');
const chatWindow = document.getElementById('chat-window');
const chatForm = document.getElementById('chat-form');
const messageInput = document.getElementById('message-input');
const sendButton = document.getElementById('send-button');

// フィードバック用の一時保存変数
let currentFeedbackTarget = {
    userMessage: "",
    aiResponse: "",
    score: 0
};

// テキストエリアの自動リサイズ処理
if (messageInput) {
    messageInput.addEventListener('input', function() {
        this.style.height = 'auto'; 
        this.style.height = (this.scrollHeight) + 'px';
        if (this.value === '') {
            this.style.height = ''; 
        }
    });

    messageInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault(); 
            if (chatForm) {
                if (typeof chatForm.requestSubmit === 'function') {
                    chatForm.requestSubmit();
                } else {
                    chatForm.dispatchEvent(new Event('submit', { cancelable: true }));
                }
            }
        }
    });
}

function addChatMessage(sender, message) {
    if(!chatWindow) return;
    const messageWrapper = document.createElement('div');
    messageWrapper.classList.add('message', sender === 'user' ? 'user-message' : 'ai-message');
    const messageBubble = document.createElement('div');
    messageBubble.classList.add('message-bubble');
    
    const urlRegex = /((https?:\/\/[^\s]+)|(data\/[^\s]+))/g;
    
    let formattedMessage = message.replace(urlRegex, (match) => {
        let url = match;
        if (url.startsWith('data/')) url = '/' + url;
        let displayText = match;
        if (match.startsWith('data/')) {
            const filename = match.split('/').pop();
            displayText = `📄 ${filename}`;
        }
        return `<a href="${url}" target="_blank" rel="noopener noreferrer">${displayText}</a>`;
    });
    
    formattedMessage = formattedMessage.replace(
        /\[AIセミナー:\s*(.*?)\]\((.*?)\)/g, 
        '<button class="chat-link-btn seminar" onclick="startSeminar(\'$2\')"><i class="fas fa-chalkboard-teacher"></i> 「$1」を受講する</button>'
    );
    formattedMessage = formattedMessage.replace(
        /\[音声教材:\s*(.*?)\]\((.*?)\)/g, 
        (match, title, url) => {
            const safeTitle = title.replace(/'/g, "\\'");
            return `<button class="chat-link-btn audio" onclick="playMaterialAudio('${url}', '${safeTitle}')"><i class="fas fa-volume-up"></i> 音声教材: ${title}</button>`;
        }
    );
    formattedMessage = formattedMessage.replace(
        /\[(教科書|関連資料):\s*(.*?)\]\((.*?)\)/g, 
        '<a href="$3" target="_blank" class="chat-link-btn pdf"><i class="fas fa-file-pdf"></i> $1: $2</a>'
    );

    formattedMessage = formattedMessage.replace(/\n/g, '<br>');
    messageBubble.innerHTML = formattedMessage;
    
    messageWrapper.appendChild(messageBubble);
    chatWindow.appendChild(messageWrapper);
    chatWindow.scrollTop = chatWindow.scrollHeight;
    return messageWrapper;
}

function addAiMessageWithTime(messageWrapper, message, time, audioUrl) {
    if(!messageWrapper) return;
    const urlRegex = /((https?:\/\/[^\s]+)|(data\/[^\s]+))/g;
    let formattedMessage = message.replace(urlRegex, (match) => {
        let url = match;
        if (url.startsWith('data/')) url = '/' + url;
        let displayText = match;
        if (match.startsWith('data/')) {
            const filename = match.split('/').pop();
            displayText = `📄 ${filename}`;
        }
        return `<a href="${url}" target="_blank" rel="noopener noreferrer">${displayText}</a>`;
    });
    
    formattedMessage = formattedMessage.replace(
        /\[AIセミナー:\s*(.*?)\]\((.*?)\)/g, 
        '<button class="chat-link-btn seminar" onclick="startSeminar(\'$2\')"><i class="fas fa-chalkboard-teacher"></i> 「$1」を受講する</button>'
    );
    formattedMessage = formattedMessage.replace(
        /\[音声教材:\s*(.*?)\]\((.*?)\)/g, 
        (match, title, url) => {
            const safeTitle = title.replace(/'/g, "\\'");
            return `<button class="chat-link-btn audio" onclick="playMaterialAudio('${url}', '${safeTitle}')"><i class="fas fa-volume-up"></i> 音声教材: ${title}</button>`;
        }
    );
    formattedMessage = formattedMessage.replace(
        /\[(教科書|関連資料):\s*(.*?)\]\((.*?)\)/g, 
        '<a href="$3" target="_blank" class="chat-link-btn pdf"><i class="fas fa-file-pdf"></i> $1: $2</a>'
    );

    formattedMessage = formattedMessage.replace(/\n/g, '<br>');
    messageWrapper.querySelector('.message-bubble').innerHTML = formattedMessage;
    
    let timeElement = messageWrapper.querySelector('.elapsed-time');
    if (!timeElement) {
        timeElement = document.createElement('div');
        timeElement.classList.add('elapsed-time');
        messageWrapper.appendChild(timeElement);
    }
    timeElement.innerText = `応答時間: ${time}秒`;
    
    if (audioUrl) {
        playAudio(audioUrl);
    }
}

function playAudio(url) {
    if (url) {
        audioPlayer.src = url;
        audioPlayer.play().catch(e => console.error('[Audio] 再生エラー:', e));
    }
}

function addFeedbackButtons(messageWrapper, userMessage, aiResponse) {
    if(!messageWrapper) return;
    const feedbackContainer = document.createElement('div');
    feedbackContainer.classList.add('feedback-container');
    
    const goodBtn = document.createElement('button');
    goodBtn.classList.add('feedback-button');
    goodBtn.innerHTML = '👍';
    goodBtn.onclick = () => handleFeedback(messageWrapper, userMessage, aiResponse, 1, goodBtn, badBtn);
    
    const badBtn = document.createElement('button');
    badBtn.classList.add('feedback-button');
    badBtn.innerHTML = '👎';
    badBtn.onclick = () => handleFeedback(messageWrapper, userMessage, aiResponse, 0, goodBtn, badBtn);
    
    feedbackContainer.appendChild(goodBtn);
    feedbackContainer.appendChild(badBtn);
    messageWrapper.appendChild(feedbackContainer);
}

function handleFeedback(messageWrapper, userMessage, aiResponse, score, goodBtn, badBtn) {
    if (score === 1) {
        goodBtn.classList.add('active-good');
        badBtn.classList.remove('active-bad');
        submitFeedback(userMessage, aiResponse, score, '');
        
        const feedbackMsg = document.createElement('div');
        feedbackMsg.classList.add('feedback-message');
        feedbackMsg.innerText = 'フィードバックありがとうございます!';
        messageWrapper.appendChild(feedbackMsg);
        goodBtn.disabled = true;
        badBtn.disabled = true;
    } else {
        badBtn.classList.add('active-bad');
        goodBtn.classList.remove('active-good');
        
        currentFeedbackTarget = {
            userMessage: userMessage,
            aiResponse: aiResponse,
            score: 0
        };
        
        const feedbackModal = document.getElementById('feedbackModal');
        if (feedbackModal) {
            feedbackModal.style.display = 'flex';
        }
        
        goodBtn.disabled = true;
        badBtn.disabled = true;
    }
}

// フィードバックモーダルのボタンイベントを初期化時に設定
document.addEventListener('DOMContentLoaded', () => {
    const submitBtn = document.getElementById('submitBadFeedbackButton');
    const cancelBtn = document.getElementById('cancelFeedbackButton');
    const feedbackModal = document.getElementById('feedbackModal');
    const commentBox = document.getElementById('feedbackComment');

    if (submitBtn) {
        submitBtn.onclick = () => {
            const comment = commentBox.value;
            // メッセージが空の場合（Flutter旗ボタンからの報告など）はデフォルト値を設定
            const uMsg = currentFeedbackTarget.userMessage || "（アプリ不具合・意見報告）";
            const aResp = currentFeedbackTarget.aiResponse || "（なし）";
            
            submitFeedback(uMsg, aResp, 0, comment);
            
            feedbackModal.style.display = 'none';
            commentBox.value = '';
            
            currentFeedbackTarget = { userMessage: "", aiResponse: "", score: 0 };
        };
    }

    if (cancelBtn) {
        cancelBtn.onclick = () => {
            feedbackModal.style.display = 'none';
            commentBox.value = '';
            currentFeedbackTarget = { userMessage: "", aiResponse: "", score: 0 };
        };
    }
});

async function submitFeedback(userMessage, aiResponse, score, comment) {
    try {
        await fetch('/submit_feedback', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                user_message: userMessage,
                ai_response: aiResponse,
                score: score,
                comment: comment
            })
        });
    } catch (e) {
        console.error('[Feedback] 送信エラー:', e);
    }
}

if(chatForm) {
    chatForm.addEventListener('submit', async (event) => {
        event.preventDefault();
        const userMessage = messageInput.value.trim();
        if (userMessage === '') return;
        
        sendButton.disabled = true;
        messageInput.disabled = true; 
        addChatMessage('user', userMessage);
        messageInput.value = '';
        messageInput.style.height = ''; 
        
        // 地球儀表示
        const earth = document.getElementById('earthSpinner');
        if(earth) earth.style.display = 'flex';

        const startTime = performance.now();

        try {
            // 1次応答
            const interimResponse = await fetch('/chat', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ message: userMessage })
            });
            
            if (!interimResponse.ok) throw new Error(`サーバーエラー: ${interimResponse.status}`);
            
            const interimData = await interimResponse.json();

            // 即答パターン（定型文など）の場合
            if (interimData.final_response) {
                if(earth) earth.style.display = 'none'; // 地球儀消す
                
                const endTime = performance.now();
                const elapsedTime = ((endTime - startTime) / 1000).toFixed(2);
                
                const finalMessageDiv = addChatMessage('ai', interimData.final_response);
                addAiMessageWithTime(finalMessageDiv, interimData.final_response, elapsedTime, interimData.final_audio_url);
                addFeedbackButtons(finalMessageDiv, userMessage, interimData.final_response);
                
                sendButton.disabled = false;
                messageInput.disabled = false;
                messageInput.focus();
                return;
            }

            // 通常パターン：1次音声再生しつつ2次処理へ
            if (interimData.interim_audio_url) {
                // 音声だけ再生（テキストは表示しない）
                audioPlayer.src = interimData.interim_audio_url;
                audioPlayer.play().catch(()=>{}); 
            }
            
            // 2次応答（本処理）
            const finalResponse = await fetch('/process_chat', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ message: userMessage })
            });
            
            if (!finalResponse.ok) throw new Error(`サーバーエラー: ${finalResponse.status}`);
            
            const finalData = await finalResponse.json();
            
            // 処理完了、地球儀消す
            if(earth) earth.style.display = 'none';

            const endTime = performance.now();
            const elapsedTime = ((endTime - startTime) / 1000).toFixed(2);
            
            const finalMessageDiv = addChatMessage('ai', finalData.final_response);
            addAiMessageWithTime(finalMessageDiv, finalData.final_response, elapsedTime, finalData.final_audio_url);
            addFeedbackButtons(finalMessageDiv, userMessage, finalData.final_response);
            
        } catch (error) {
            // エラー時も地球儀消す
            if(earth) earth.style.display = 'none';
            
            addChatMessage('ai', 'エラーが発生しました。もう一度お試しください。');
            console.error(error);
        } finally {
            sendButton.disabled = false;
            messageInput.disabled = false;
            messageInput.focus();
        }
    });
}

// ========================================
// オフライン検知機能
// ========================================
(function() {
    const offlineScreen = document.getElementById('offlineScreen');
    const icon = offlineScreen ? offlineScreen.querySelector('i') : null;

    function updateOnlineStatus() {
        if (!offlineScreen) return;

        if (navigator.onLine) {
            // オンライン時: 画面を隠す
            offlineScreen.style.display = 'none';
        } else {
            // オフライン時: 画面を表示
            offlineScreen.style.display = 'flex';
            
            // アイコンを切り替え (FontAwesomeのバージョンによってslashが効かない場合への対策)
            if (icon) {
                icon.className = 'fas fa-wifi-slash offline-icon';
            }
        }
    }

    // イベントリスナー登録
    window.addEventListener('online', updateOnlineStatus);
    window.addEventListener('offline', updateOnlineStatus);

    // 初回ロード時にもチェック
    window.addEventListener('load', updateOnlineStatus);
    
    // 即時実行
    updateOnlineStatus();
})();