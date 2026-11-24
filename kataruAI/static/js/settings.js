/* ゲーム設定：変更したらすぐ保存（イベント47・48）
   本番：fetch でPOST（X-CSRFToken付き）。失敗したら元の値に戻して「保存に失敗しました」 */
(function () {
  "use strict";

  const SAMPLE = "いらっしゃい。……悪いけど、もうすぐ閉店だよ。";
  const SPEED_MS = { slow: 90, normal: 45, fast: 15 }; // 1文字あたりの表示間隔（仮）
  const mockError = new URLSearchParams(location.search).get("mock") === "error";
  const sampleEl = document.getElementById("sample-text");
  let typingTimer = null;

  // 見本テキストを1文字ずつ表示（プレイ画面でも同じ仕組みを使う想定）
  function playSample(speed) {
    clearInterval(typingTimer);
    let i = 0;
    sampleEl.textContent = "";
    typingTimer = setInterval(function () {
      i += 1;
      sampleEl.textContent = SAMPLE.slice(0, i);
      if (i >= SAMPLE.length) clearInterval(typingTimer);
    }, SPEED_MS[speed]);
  }

  // モックの保存処理
  function save() {
    return new Promise(function (resolve, reject) {
      setTimeout(mockError ? reject : resolve, 300);
    });
  }

  /* テキスト速度 */
  let currentSpeed = document.querySelector('input[name="text_speed"]:checked').value;
  document.querySelectorAll('input[name="text_speed"]').forEach(function (radio) {
    radio.addEventListener("change", function () {
      const prev = currentSpeed;
      save().then(function () {
        currentSpeed = radio.value;
        playSample(currentSpeed);
      }).catch(function () {
        document.getElementById("speed-" + prev).checked = true; // 変更前に戻す
        window.Kataru.toast("保存に失敗しました", "error");
      });
    });
  });

  /* 自動保存トグル */
  const toggle = document.getElementById("auto-save");
  toggle.addEventListener("change", function () {
    const next = toggle.checked;
    save().then(function () {
      window.Kataru.toast(next ? "自動保存をオンにしました" : "自動保存をオフにしました");
    }).catch(function () {
      toggle.checked = !next; // 変更前に戻す
      window.Kataru.toast("保存に失敗しました", "error");
    });
  });

  playSample(currentSpeed);
})();
