/* シナリオ一覧・お気に入り一覧：詳細オーバーレイ（イベント27）とコード検索（イベント52） */
(function () {
  "use strict";

  const LEVEL = { beginner: "初級", intermediate: "中級", advanced: "上級" };
  const $ = function (id) { return document.getElementById(id); };

  /* ---------- 詳細オーバーレイに行のデータを入れる ---------- */
  function fillDetail(d) {
    $("detail-name").textContent = d.name;
    const lv = $("detail-level");
    lv.textContent = LEVEL[d.level];
    lv.className = "lv lv--" + d.level;
    $("detail-desc").textContent = d.desc;
    $("detail-author").textContent = "作成：" + d.author;
    $("detail-plays").textContent = d.plays + "回プレイ";
    $("detail-best").textContent = d.best;
    $("detail-goal").textContent = d.goal;
    $("detail-cond").textContent = d.cond;
    $("detail-face").src = "../static/img/" + d.face;
    const fav = $("detail-fav");
    const on = d.fav === "true";
    fav.setAttribute("aria-pressed", String(on));
    fav.textContent = on ? "★ お気に入り登録済み" : "☆ お気に入りに登録";
  }

  document.querySelectorAll("li[data-open='overlay-detail']").forEach(function (row) {
    // data-open のクリックで common.js が開く。その前にデータを入れる（capture で先に動かす）
    row.addEventListener("click", function () {
      const favBtn = row.querySelector(".icon-btn--fav");
      if (favBtn) row.dataset.fav = favBtn.getAttribute("aria-pressed");
      fillDetail(row.dataset);
    }, true);
    // キーボード操作（Enter）でも開く
    row.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && e.target === row) row.click();
    });
  });

  /* ---------- コード検索（イベント52） ---------- */
  const form = $("code-form");
  if (!form) return;
  const input = $("share-code");
  const error = $("code-error");
  const MOCK_CODE = "A1B2C3D4"; // 本番：GET /scenarios/code/<code>/ などでサーバーに問い合わせる

  function showError(msg) {
    error.textContent = msg;
    error.hidden = false;
    input.classList.add("is-error");
  }

  input.addEventListener("input", function () {
    input.value = input.value.toUpperCase();
    error.hidden = true;
    input.classList.remove("is-error");
  });

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    const code = input.value.trim();
    if (!/^[A-Z0-9]{8}$/.test(code)) {
      showError("8桁の英数字で入力してね。");
      return;
    }
    if (code !== MOCK_CODE) {
      showError("そのコードのシナリオは見つかりません");
      return;
    }
    // 取得成功 → コード検索を閉じて詳細を開く
    window.Kataru.closeOverlay(form.closest(".overlay"));
    const first = document.querySelector("li[data-open='overlay-detail']");
    if (first) fillDetail(first.dataset);
    window.Kataru.openOverlay("overlay-detail");
  });
})();
