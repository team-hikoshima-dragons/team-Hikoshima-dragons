/* トップ画面：ゲーム開始（イベント9・12）と難易度説明の切り替え
   POST /api/plays/ → 成功したら返ってきた play_url（プレイ画面）へ移動する。
   失敗したら生成エラーの表示を出す（再試行できる）。 */
(function () {
  "use strict";

  const startBtn = document.getElementById("start-btn");
  const loading = document.getElementById("overlay-generating");
  const error = document.getElementById("overlay-gen-error");
  const retryBtn = document.getElementById("retry-btn");
  // Django が配る csrftoken の Cookie を読む（POST で X-CSRFToken ヘッダーに入れる。AGENTS.md §6）
  function getCookie(name) {
    const prefix = name + "=";
    const found = document.cookie.split("; ").find(function (row) { return row.startsWith(prefix); });
    return found ? decodeURIComponent(found.slice(prefix.length)) : "";
  }

  const errorText = document.getElementById("gen-error-text");

  function showError(message) {
    loading.hidden = true;
    startBtn.disabled = false;
    // サーバーからメッセージが返ってきたら、それを表示する（例：シナリオが削除されていた）
    if (errorText && typeof message === "string" && message) errorText.textContent = message;
    if (error) error.hidden = false;
  }

  function startGame() {
    if (error) error.hidden = true;
    loading.hidden = false;
    startBtn.disabled = true; // 生成中はプレイボタンを無効化（No.22）

    // 会員の「もう一度挑戦する」（リザルト）は同じシナリオで始める（イベント22）
    // それ以外は、難易度の選択がある画面ならそれを送る（ゲストはサーバー側で初級固定）
    const checked = document.querySelector('input[name="difficulty"]:checked');
    const scenarioId = startBtn.dataset.scenarioId;
    // ゲストのリザルトの「もう一度挑戦する」は、セッションに持っているお題で始める（data-retry）
    const body = startBtn.dataset.retry !== undefined ? { retry: true }
      : scenarioId ? { scenario_id: Number(scenarioId) }
      : checked ? { difficulty: checked.value } : {};

    fetch("/api/plays/", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": getCookie("csrftoken") },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(45000) // サーバー側の Gemini 待ち（25秒）より長めに待つ
    })
      .then(function (res) {
        return res.json().catch(function () { return null; }).then(function (data) {
          if (res.ok && data && data.play_url) {
            location.href = data.play_url; // 成功：プレイ画面へ
          } else {
            showError(data && data.error && data.error.message);
          }
        });
      })
      .catch(function () { showError(); }); // 通信そのものの失敗（タイムアウトなど）
  }

  if (startBtn) startBtn.addEventListener("click", startGame);
  if (retryBtn) retryBtn.addEventListener("click", startGame);

  /* 難易度説明（トップ(ログイン済み) No.11） */
  const desc = document.getElementById("difficulty-desc");
  const texts = {
    beginner: "初級：15ターン。相手が話を聞いてくれやすい。",
    intermediate: "中級：12ターン。標準ルール。",
    advanced: "上級：10ターン。相手が手ごわく、疑い深い。"
  };
  document.querySelectorAll('input[name="difficulty"]').forEach(function (radio) {
    radio.addEventListener("change", function () {
      if (desc) desc.textContent = texts[radio.value];
    });
  });
})();
