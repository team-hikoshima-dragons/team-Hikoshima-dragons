/* トップ画面：ゲーム開始（イベント9・12）と難易度説明の切り替え
   本番：POST /api/plays/ → 成功したら返ってきた play_id でプレイ画面へ。
   モック：URLに ?mock=error を付けると生成失敗の表示を確認できる */
(function () {
  "use strict";

  const startBtn = document.getElementById("start-btn");
  const loading = document.getElementById("overlay-generating");
  const error = document.getElementById("overlay-gen-error");
  const retryBtn = document.getElementById("retry-btn");
  const mockError = new URLSearchParams(location.search).get("mock") === "error";

  function startGame() {
    if (error) error.hidden = true;
    loading.hidden = false;
    startBtn.disabled = true; // 生成中はプレイボタンを無効化（No.22）

    // ↓ 本番はここを fetch に置き換える
    setTimeout(function () {
      loading.hidden = true;
      startBtn.disabled = false;
      if (mockError) {
        error.hidden = false;
      } else {
        location.href = "play.html";
      }
    }, 1500);
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
