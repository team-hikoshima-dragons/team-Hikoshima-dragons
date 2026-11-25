/* シナリオ一覧・お気に入り一覧
   - 詳細オーバーレイ（イベント27）：押した行の data-* を textContent で入れる
   - お気に入りの登録・解除（イベント28）：POST /scenarios/{id}/favorite/。失敗したら元に戻す
   - 開始（イベント29）：POST /api/plays/ に scenario_id を送り、プレイ画面へ
   - コード検索（イベント52）：GET /scenarios/code/{code}/ */
(function () {
  "use strict";

  const LEVEL = { beginner: "初級", intermediate: "中級", advanced: "上級" };
  const $ = function (id) { return document.getElementById(id); };
  const onFavoritesPage = location.pathname.indexOf("/scenarios/favorites/") === 0;
  let current = null; // 詳細オーバーレイに表示中のシナリオ

  function getCookie(name) {
    const prefix = name + "=";
    const found = document.cookie.split("; ").find(function (row) { return row.startsWith(prefix); });
    return found ? decodeURIComponent(found.slice(prefix.length)) : "";
  }

  // JSON を返す通信。失敗したらサーバーのメッセージ付きで reject する
  function request(method, url, body) {
    const options = { method: method, credentials: "same-origin", headers: { "X-CSRFToken": getCookie("csrftoken") } };
    if (body) {
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(body);
    }
    return fetch(url, options).then(function (res) {
      return res.json().catch(function () { return null; }).then(function (data) {
        if (!res.ok || !data) {
          throw new Error((data && data.error && data.error.message) || "通信エラーが発生しました");
        }
        return data;
      });
    });
  }

  /* ---------- 詳細オーバーレイ ---------- */
  function setFavButton(on) {
    const fav = $("detail-fav");
    fav.setAttribute("aria-pressed", String(on));
    fav.textContent = on ? "★ お気に入り登録済み" : "☆ お気に入りに登録";
  }

  function fillDetail(d) {
    current = d;
    $("detail-name").textContent = d.name;
    const lv = $("detail-level");
    lv.textContent = LEVEL[d.level] || "";
    lv.className = "lv lv--" + d.level;
    $("detail-desc").textContent = d.desc;
    $("detail-author").textContent = "作成：" + d.author;
    $("detail-plays").textContent = d.plays + "回プレイ";
    $("detail-best").textContent = d.best;
    $("detail-goal").textContent = d.goal;
    $("detail-cond").textContent = d.cond;
    $("detail-face").src = d.image;
    $("detail-error").hidden = true;
    setFavButton(d.fav === true || d.fav === "true");
  }

  document.querySelectorAll("li[data-open='overlay-detail']").forEach(function (row) {
    // data-open のクリックで common.js が開く。その前にデータを入れる（capture で先に動かす）
    row.addEventListener("click", function () {
      fillDetail(Object.assign({}, row.dataset));
    }, true);
    row.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && e.target === row) row.click();
    });
  });

  /* ---------- お気に入り（一覧の★と詳細のボタン） ---------- */
  function rowOf(id) {
    return document.querySelector("li[data-id='" + String(Number(id)) + "']");
  }

  function applyFavorite(id, on, count) {
    const row = rowOf(id);
    if (row) {
      row.dataset.fav = String(on);
      const btn = row.querySelector(".icon-btn--fav");
      btn.setAttribute("aria-pressed", String(on));
      btn.setAttribute("aria-label", on ? "お気に入りを解除" : "お気に入りに登録");
      if (typeof count === "number") row.querySelector("[data-fav-count]").textContent = "★" + count;
      if (!on && onFavoritesPage) row.remove(); // お気に入り一覧では、解除すると一覧から消える
    }
    if (current && String(current.id) === String(id)) {
      current.fav = on;
      setFavButton(on);
    }
  }

  function toggleFavorite(id, wasOn) {
    applyFavorite(id, !wasOn); // すぐ表示を変える
    request("POST", "/scenarios/" + Number(id) + "/favorite/").then(function (data) {
      applyFavorite(id, data.favorited, data.favorite_count);
      window.Kataru.toast(data.favorited ? "お気に入りに登録しました" : "お気に入りを解除しました");
    }).catch(function () {
      applyFavorite(id, wasOn); // 元に戻す
      window.Kataru.toast("保存に失敗しました", "error");
    });
  }

  document.addEventListener("click", function (e) {
    const btn = e.target.closest(".icon-btn--fav");
    if (!btn) return;
    e.stopPropagation();
    const row = btn.closest("li");
    toggleFavorite(row.dataset.id, btn.getAttribute("aria-pressed") === "true");
  }, true);

  $("detail-fav").addEventListener("click", function () {
    if (!current) return;
    toggleFavorite(current.id, $("detail-fav").getAttribute("aria-pressed") === "true");
  });

  /* ---------- 開始（イベント29） ---------- */
  $("detail-start").addEventListener("click", function () {
    if (!current) return;
    const btn = $("detail-start");
    btn.disabled = true;
    request("POST", "/api/plays/", { scenario_id: Number(current.id) }).then(function (data) {
      location.href = data.play_url;
    }).catch(function (err) {
      btn.disabled = false;
      $("detail-error").textContent = err.message;
      $("detail-error").hidden = false;
    });
  });

  /* ---------- コード検索（イベント52） ---------- */
  const form = $("code-form");
  const input = $("share-code");
  const error = $("code-error");

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
    request("GET", "/scenarios/code/" + encodeURIComponent(code) + "/").then(function (data) {
      window.Kataru.closeOverlay(form.closest(".overlay"));
      fillDetail(data);
      window.Kataru.openOverlay("overlay-detail");
    }).catch(function (err) {
      showError(err.message);
    });
  });
})();
