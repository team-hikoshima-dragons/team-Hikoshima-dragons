/* プレイ画面のモック（イベント31〜34・49）
   本番は React で作り、mockReply() の部分を POST /api/plays/{id}/turns/ に置き換える。
   サーバーが返すのは「返答・いまの様子・表情・残りターン・status」だけ（数値は返さない） */
(function () {
  "use strict";

  const $ = function (id) { return document.getElementById(id); };
  const log = $("log");
  const talk = $("talk");
  const form = $("composer");
  const textarea = $("message");
  const sendBtn = $("send-btn");
  const errorArea = $("error-area");
  const goalArea = $("goal-area");
  const MAX = 120;

  let turnsLeft = Number($("turns-left").textContent);
  let sending = false;
  let lastMessage = "";
  let sentCount = 0;
  let failOnce = new URLSearchParams(location.search).get("mock") === "error";

  /* ---------- 送信ボタンの有効／無効（イベント34） ---------- */
  function refreshSend() {
    const len = textarea.value.length;
    sendBtn.disabled = sending || len === 0 || len > MAX || textarea.value.trim() === "";
  }
  textarea.addEventListener("input", refreshSend);

  // Enterで送信、Shift+Enterで改行（IME変換中は送らない）
  textarea.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      if (!sendBtn.disabled) form.requestSubmit();
    }
  });

  /* ---------- 吹き出しを追加 ---------- */
  function addBubble(type, text, face) {
    const tpl = $(type === "user" ? "tpl-user" : "tpl-opp");
    const node = tpl.content.firstElementChild.cloneNode(true);
    node.querySelector(".talk__bubble").textContent = text; // innerHTML禁止
    if (face) node.querySelector("img").src = "../static/img/face-" + face + ".svg";
    talk.appendChild(node);
    scrollBottom();
    return node;
  }
  function addTyping() {
    const el = document.createElement("p");
    el.className = "talk__typing";
    el.textContent = $("opp-name").textContent + "が考えています"; // No.16
    talk.appendChild(el);
    scrollBottom();
    return el;
  }
  function addNotice(text) {
    const el = document.createElement("p");
    el.className = "talk__notice";
    el.textContent = text;
    talk.appendChild(el);
    scrollBottom();
  }
  function scrollBottom() { log.scrollTop = log.scrollHeight; }

  /* ---------- 状態の更新 ---------- */
  const MOOD_LABEL = { normal: "迷っている", happy: "心が動いている", angry: "イライラしている", doubt: "疑っている" };
  function updateState(res) {
    $("opp-face").src = "../static/img/face-" + res.face + ".svg";
    $("opp-face-box").dataset.mood = res.face;
    $("mood-text").textContent = res.mood;
    turnsLeft = res.turnsLeft;
    $("turns-left").textContent = String(turnsLeft);
    $("turns").classList.toggle("is-low", turnsLeft <= 3);
  }

  /* ---------- モックの返答（本番は fetch） ---------- */
  const SCRIPT = [
    { text: "ふん、常連のためって言うけどな。こっちも体がもたんのよ。", face: "doubt" },
    { text: "片付けを手伝う？……口だけじゃないだろうな。", face: "normal" },
    { text: "そこまで言うなら、考えてやらんこともない。", face: "happy" },
    { text: "……わかったよ。今日だけだぞ。", face: "happy", status: "cleared" }
  ];
  function mockReply(message) {
    return new Promise(function (resolve, reject) {
      setTimeout(function () {
        if (failOnce) { failOnce = false; reject({ code: "AI_ERROR" }); return; }
        if (message.indexOf("バカ") !== -1) { reject({ code: "BLOCKED" }); return; }
        const s = SCRIPT[Math.min(sentCount, SCRIPT.length - 1)];
        sentCount += 1;
        resolve({
          reply: s.text, face: s.face, mood: s.status === "cleared" ? "納得した" : MOOD_LABEL[s.face],
          turnsLeft: turnsLeft - 1, status: s.status || (turnsLeft - 1 <= 0 ? "failed" : "playing")
        });
      }, 1200);
    });
  }

  /* ---------- 送信（イベント33・49） ---------- */
  function send(message, withBubble) {
    sending = true;
    refreshSend();
    errorArea.hidden = true;
    if (withBubble) addBubble("user", message);
    const typing = addTyping();

    mockReply(message).then(function (res) {
      typing.remove();
      addBubble("opp", res.reply, res.face);
      updateState(res);
      if (res.status === "cleared") {
        form.hidden = true;
        goalArea.hidden = false;
      } else if (res.status === "failed") {
        location.href = "result.html?fail=1";
      }
    }).catch(function (err) {
      typing.remove();
      if (err.code === "BLOCKED") {
        addNotice("その発言は送れないよ。言い方を変えてみてね（ターンは消費していません）");
      } else {
        errorArea.hidden = false;
      }
    }).finally(function () {
      sending = false;
      refreshSend();
    });
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    const message = textarea.value;
    if (!message.trim() || message.length > MAX || sending) return;
    lastMessage = message;
    textarea.value = "";
    textarea.dispatchEvent(new Event("input")); // 文字数表示を更新
    send(message, true);
  });

  $("retry-btn").addEventListener("click", function () { send(lastMessage, false); });
  $("cancel-btn").addEventListener("click", function () { errorArea.hidden = true; });

  /* ---------- 中断・あきらめる（イベント31・32） ---------- */
  $("logo-link").addEventListener("click", function (e) {
    if (!goalArea.hidden) return; // クリア後はそのまま戻れる
    if (!confirm("プレイを中断しますか？")) e.preventDefault();
    // 本番：OKなら POST /api/plays/{id}/abort/ → トップへ
  });
  $("give-up-btn").addEventListener("click", function () {
    if (confirm("あきらめますか？")) {
      // 本番：POST /api/plays/{id}/give-up/ → リザルトへ
      location.href = "result.html?fail=1";
    }
  });

  refreshSend();
  scrollBottom();
})();
