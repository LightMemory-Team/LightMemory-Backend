// 親友分享頁：填暱稱 → 看日記 → 留言
// 留言 API：POST /api/share/<share_token>/comments/  body: { nickname, content }

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

  // 開頁時：存過暱稱就直接看日記，沒有就先填暱稱
  if (nickname) {
    showPostStep();
  } else {
    showNicknameStep();
  }
})();
