// 親友分享頁：填暱稱 → 看日記 → 錄語音加油／打字留言
// 留言 API：POST /api/share/<share_token>/comments/  body: { nickname, content }
// 語音加油 API：POST /api/share/<share_token>/voice-replies/
//   multipart：nickname、audio_file、duration_sec（最多 10 秒）

(function () {
  const NICKNAME_KEY = 'lightmemory_share_nickname';
  const MAX_LENGTH = 200;
  const shareToken = document.body.dataset.shareToken;

  // 用檔案直接打開預覽時（file://）沒有後端，送出改成假裝成功
  const isPreview = window.location.protocol === 'file:';

  const nicknameStep = document.getElementById('nickname-step');
  const postStep = document.getElementById('post-step');
  const nicknameForm = document.getElementById('nickname-form');
  const nicknameInput = document.getElementById('nickname-input');
  const nicknameError = document.getElementById('nickname-error');
  const nicknameDisplay = document.getElementById('nickname-display');
  const changeNicknameBtn = document.getElementById('change-nickname');

  const commentForm = document.getElementById('comment-form');
  const commentInput = document.getElementById('comment-input');
  const commentError = document.getElementById('comment-error');
  const commentSubmit = document.getElementById('comment-submit');
  const sentList = document.getElementById('sent-list');

  // 有些瀏覽器（例如無痕模式）不能用 localStorage，讀寫失敗就當作沒存過
  function loadNickname() {
    try {
      return localStorage.getItem(NICKNAME_KEY) || '';
    } catch (e) {
      return '';
    }
  }

  function saveNickname(name) {
    try {
      localStorage.setItem(NICKNAME_KEY, name);
    } catch (e) {
      // 存不了就算了，這次頁面還是能用
    }
  }

  let nickname = loadNickname();

  function showError(el, message) {
    el.textContent = message;
    el.hidden = false;
  }

  function hideError(el) {
    el.textContent = '';
    el.hidden = true;
  }

  function showNicknameStep() {
    nicknameInput.value = nickname;
    hideError(nicknameError);
    postStep.hidden = true;
    nicknameStep.hidden = false;
    window.scrollTo(0, 0);
    nicknameInput.focus();
  }

  function showPostStep() {
    nicknameDisplay.textContent = nickname;
    nicknameStep.hidden = true;
    postStep.hidden = false;
    window.scrollTo(0, 0);
  }

  // 第 1 步：暱稱
  nicknameForm.addEventListener('submit', function (event) {
    event.preventDefault();
    const value = nicknameInput.value.trim();
    if (value.length < 1 || value.length > 12) {
      showError(nicknameError, '暱稱請填 1 到 12 個字');
      return;
    }
    nickname = value;
    saveNickname(nickname);
    showPostStep();
  });

  changeNicknameBtn.addEventListener('click', showNicknameStep);

  // 第 2 步：留言框隨內容長高；快到上限才提示字數
  commentInput.addEventListener('input', function () {
    commentInput.style.height = 'auto';
    commentInput.style.height = commentInput.scrollHeight + 'px';

    const left = MAX_LENGTH - commentInput.value.length;
    if (left <= 20) {
      showError(commentError, '還可以寫 ' + left + ' 個字');
    } else {
      hideError(commentError);
    }
  });

  function addSentItem(name, content) {
    const li = document.createElement('li');
    const nameEl = document.createElement('span');
    nameEl.className = 'sent-name';
    nameEl.textContent = name;
    const textEl = document.createElement('span');
    textEl.textContent = content;
    const markEl = document.createElement('span');
    markEl.className = 'sent-mark';
    markEl.textContent = '已送出';
    li.appendChild(nameEl);
    li.appendChild(textEl);
    li.appendChild(markEl);
    sentList.appendChild(li);
    sentList.hidden = false;
  }

  async function postComment(content) {
    if (isPreview) {
      await new Promise(function (resolve) { setTimeout(resolve, 500); });
      return { ok: true, data: { nickname: nickname, content: content } };
    }

    let response;
    try {
      response = await fetch('/api/share/' + encodeURIComponent(shareToken) + '/comments/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ nickname: nickname, content: content }),
      });
    } catch (e) {
      return { ok: false, message: '網路不太穩，請再試一次' };
    }

    let json = null;
    try {
      json = await response.json();
    } catch (e) {
      // 回傳的不是 JSON，下面用預設訊息
    }

    if (response.ok && json && json.success) {
      return { ok: true, data: json.data };
    }

    const message = json && json.error && json.error.message
      ? json.error.message
      : '沒有送出去，請再試一次';
    return { ok: false, code: json && json.error ? json.error.code : null, message: message };
  }

  commentForm.addEventListener('submit', async function (event) {
    event.preventDefault();
    hideError(commentError);

    const content = commentInput.value.trim();
    if (!content) {
      showError(commentError, '先寫一句話再發送');
      return;
    }

    commentSubmit.disabled = true;
    const result = await postComment(content);
    commentSubmit.disabled = false;

    if (result.ok) {
      addSentItem(result.data.nickname, result.data.content);
      commentInput.value = '';
      commentInput.style.height = '';
      return;
    }

    // 暱稱被後端擋下時，回到第 1 步重填
    if (result.code === 'INVALID_NICKNAME') {
      showNicknameStep();
      showError(nicknameError, result.message);
      return;
    }

    showError(commentError, result.message);
  });

  // ============================================================
  // 語音加油（照比賽版 futureQ 的 share.js）
  //   待機 → 錄音中（最多 10 秒自動停止）→ 試聽 → 送出 → 完成
  // ============================================================

  const MAX_VOICE_SEC = 10;
  const micBtn = document.getElementById('vr-mic-btn');
  const micIcon = document.getElementById('vr-mic-icon');
  const vrHint = document.getElementById('vr-hint');
  const vrTimer = document.getElementById('vr-timer');
  const recordArea = document.getElementById('vr-record-area');
  const previewArea = document.getElementById('vr-preview');
  const audioPlayer = document.getElementById('vr-audio');
  const sendBtn = document.getElementById('vr-send-btn');
  const redoBtn = document.getElementById('vr-redo-btn');
  const doneArea = document.getElementById('vr-done');
  const againBtn = document.getElementById('vr-again-btn');
  const vrError = document.getElementById('vr-error');
  const cueCard = document.getElementById('cue-card');

  // 建議句：點一句放大顯示在麥克風上方，照著唸（不會直接送出文字）
  document.querySelectorAll('.suggest-chip').forEach(function (chip) {
    chip.addEventListener('click', function () {
      cueCard.textContent = '「' + chip.dataset.text + '」';
      cueCard.hidden = false;
      document.querySelectorAll('.suggest-chip').forEach(function (other) {
        other.classList.toggle('is-selected', other === chip);
      });
    });
  });

  // 瀏覽器支援的錄音格式：Chrome／Firefox 是 webm 或 ogg，iOS Safari 是 mp4
  const MIME_CANDIDATES = [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/mp4',
    'audio/ogg;codecs=opus',
    'audio/ogg',
  ];
  const EXTENSIONS = { 'audio/webm': 'webm', 'audio/mp4': 'm4a', 'audio/ogg': 'ogg' };

  function pickMimeType() {
    if (!window.MediaRecorder || typeof MediaRecorder.isTypeSupported !== 'function') {
      return '';
    }
    for (let i = 0; i < MIME_CANDIDATES.length; i++) {
      if (MediaRecorder.isTypeSupported(MIME_CANDIDATES[i])) return MIME_CANDIDATES[i];
    }
    return '';
  }

  const canRecord = !!(
    window.MediaRecorder &&
    navigator.mediaDevices &&
    typeof navigator.mediaDevices.getUserMedia === 'function'
  );

  let recorder = null;
  let stream = null;
  let chunks = [];
  let startedAt = 0;
  let timerId = null;
  let recordedBlob = null;
  let recordedSec = 0;
  let audioUrl = null;

  function formatSec(sec) {
    return '00:' + String(sec).padStart(2, '0');
  }

  function setRecordingLook(recording) {
    micBtn.classList.toggle('vr-recording', recording);
    micIcon.textContent = recording ? 'stop' : 'mic';
    micBtn.setAttribute('aria-label', recording ? '結束錄音' : '開始錄音');
    vrHint.textContent = recording ? '錄音中…再點一下結束' : '點一下開始錄音';
    vrTimer.hidden = !recording;
  }

  function showVoiceState(state) {
    recordArea.hidden = state !== 'idle' && state !== 'recording';
    previewArea.hidden = state !== 'preview';
    doneArea.hidden = state !== 'done';
    setRecordingLook(state === 'recording');
  }

  function releaseMic() {
    if (stream) {
      stream.getTracks().forEach(function (track) { track.stop(); });
      stream = null;
    }
  }

  function resetRecording() {
    if (audioUrl) URL.revokeObjectURL(audioUrl);
    audioUrl = null;
    recordedBlob = null;
    recordedSec = 0;
    audioPlayer.removeAttribute('src');
    hideError(vrError);
    showVoiceState('idle');
  }

  async function startRecording() {
    hideError(vrError);
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
      showError(vrError, '沒有取得麥克風權限，請允許使用麥克風後再試一次，或改用下方文字留言');
      return;
    }

    const mimeType = pickMimeType();
    try {
      recorder = mimeType ? new MediaRecorder(stream, { mimeType: mimeType }) : new MediaRecorder(stream);
    } catch (e) {
      releaseMic();
      showError(vrError, '這個瀏覽器無法錄音，可以改用下方文字留言');
      return;
    }

    chunks = [];
    recorder.addEventListener('dataavailable', function (event) {
      if (event.data && event.data.size > 0) chunks.push(event.data);
    });
    recorder.addEventListener('stop', onRecordingStopped);
    recorder.start();
    startedAt = Date.now();

    vrTimer.textContent = formatSec(0) + ' / ' + formatSec(MAX_VOICE_SEC);
    showVoiceState('recording');
    timerId = setInterval(function () {
      const sec = Math.min(MAX_VOICE_SEC, Math.floor((Date.now() - startedAt) / 1000));
      vrTimer.textContent = formatSec(sec) + ' / ' + formatSec(MAX_VOICE_SEC);
      if (sec >= MAX_VOICE_SEC) stopRecording(); // 10 秒自動停止
    }, 200);
  }

  function stopRecording() {
    clearInterval(timerId);
    timerId = null;
    if (recorder && recorder.state !== 'inactive') recorder.stop();
  }

  function onRecordingStopped() {
    releaseMic();
    const elapsed = (Date.now() - startedAt) / 1000;
    // 後端只收 1～10 秒（另外容許 1 秒誤差）
    recordedSec = Math.max(1, Math.min(MAX_VOICE_SEC, Math.round(elapsed)));

    // 型別只留主類型（去掉 ;codecs=…），後端用它判斷是不是音檔
    const rawType = (recorder && recorder.mimeType) || (chunks[0] && chunks[0].type) || 'audio/webm';
    const baseType = rawType.split(';')[0].trim() || 'audio/webm';
    recordedBlob = new Blob(chunks, { type: baseType });
    recorder = null;

    if (elapsed < 0.8 || recordedBlob.size === 0) {
      showVoiceState('idle');
      showError(vrError, '錄音太短了，請說一句話再點一下結束');
      return;
    }

    audioUrl = URL.createObjectURL(recordedBlob);
    audioPlayer.src = audioUrl;
    showVoiceState('preview');
  }

  async function uploadVoice() {
    if (isPreview) {
      await new Promise(function (resolve) { setTimeout(resolve, 600); });
      return { ok: true };
    }

    const baseType = recordedBlob.type || 'audio/webm';
    const ext = EXTENSIONS[baseType] || 'webm';
    const form = new FormData();
    form.append('nickname', nickname);
    form.append('duration_sec', String(recordedSec));
    form.append('audio_file', recordedBlob, 'voice_reply.' + ext);

    let response;
    try {
      response = await fetch('/api/share/' + encodeURIComponent(shareToken) + '/voice-replies/', {
        method: 'POST',
        body: form,
      });
    } catch (e) {
      return { ok: false, message: '網路不太穩，請再試一次' };
    }

    let json = null;
    try {
      json = await response.json();
    } catch (e) {
      // 回傳的不是 JSON，下面用預設訊息
    }

    if (response.ok && json && json.success) return { ok: true, data: json.data };

    return {
      ok: false,
      code: json && json.error ? json.error.code : null,
      message: json && json.error && json.error.message
        ? json.error.message
        : '沒有送出去，請再試一次',
    };
  }

  if (!canRecord) {
    // 不支援錄音的瀏覽器：說明後只保留文字留言
    recordArea.hidden = true;
    showError(vrError, '這個瀏覽器無法錄音，可以改用下方文字留言');
  } else {
    micBtn.addEventListener('click', function () {
      if (recorder && recorder.state === 'recording') {
        stopRecording();
      } else {
        startRecording();
      }
    });

    redoBtn.addEventListener('click', resetRecording);
    againBtn.addEventListener('click', resetRecording);

    sendBtn.addEventListener('click', async function () {
      if (!recordedBlob) return;
      hideError(vrError);
      sendBtn.disabled = true;
      redoBtn.disabled = true;
      sendBtn.lastChild.textContent = '送出中…';

      const result = await uploadVoice();

      sendBtn.disabled = false;
      redoBtn.disabled = false;
      sendBtn.lastChild.textContent = '送出語音加油';

      if (result.ok) {
        if (audioUrl) URL.revokeObjectURL(audioUrl);
        audioUrl = null;
        recordedBlob = null;
        audioPlayer.removeAttribute('src');
        cueCard.hidden = true;
        document.querySelectorAll('.suggest-chip').forEach(function (chip) {
          chip.classList.remove('is-selected');
        });
        showVoiceState('done');
        return;
      }

      // 暱稱被後端擋下時，回到第 1 步重填（錄好的語音保留）
      if (result.code === 'INVALID_NICKNAME') {
        showNicknameStep();
        showError(nicknameError, result.message);
        return;
      }
      showError(vrError, result.message);
    });

    showVoiceState('idle');
  }

  // 離開頁面時關掉麥克風
  window.addEventListener('pagehide', function () {
    stopRecording();
    releaseMic();
  });

  // 開頁時：存過暱稱就直接看日記，沒有就先填暱稱
  if (nickname) {
    showPostStep();
  } else {
    showNicknameStep();
  }
})();
