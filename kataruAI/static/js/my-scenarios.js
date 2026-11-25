/* 作成したシナリオ一覧：公開切替（イベント44）・削除（イベント46）
   POST /scenarios/{id}/visibility/ ・ /scenarios/{id}/delete/（X-CSRFToken付き）。
   「作成者＝本人か」はサーバー側で必ず確認している。 */
(function () {
  "use strict";

  const list = document.getElementById("my-list");
  if (!list) return;

  function getCookie(name) {
    const prefix = name + "=";
    const found = document.cookie.split("; ").find(function (row) { return row.startsWith(prefix); });
    return found ? decodeURIComponent(found.slice(prefix.length)) : "";
  }

  function post(url) {
    return fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "X-CSRFToken": getCookie("csrftoken") }
    }).then(function (res) {
      return res.json().catch(function () { return null; }).then(function (data) {
        if (!res.ok || !data) {
          const message = data && data.error && data.error.message;
          throw new Error(message || "通信エラーが発生しました");
        }
        return data;
      });
    });
  }

  list.addEventListener("click", function (e) {
    const row = e.target.closest("li");
    if (!row) return;
    const id = row.dataset.id;

    const toggleBtn = e.target.closest("[data-toggle-public]");
    if (toggleBtn) {
      toggleBtn.disabled = true;
      post("/scenarios/" + id + "/visibility/").then(function (data) {
        const next = data.is_public;
        row.dataset.public = String(next);
        const status = row.querySelector("[data-status]");
        status.textContent = next ? "公開中" : "非公開";
        status.className = "badge " + (next ? "badge--public" : "badge--private");
        toggleBtn.textContent = next ? "非公開にする" : "公開する";
        toggleBtn.classList.toggle("btn--primary", !next);
        window.Kataru.toast(next ? "公開しました" : "非公開にしました");
      }).catch(function (err) {
        window.Kataru.toast(err.message, "error");
      }).then(function () {
        toggleBtn.disabled = false;
      });
      return;
    }

    if (e.target.closest("[data-delete]")) {
      if (!confirm("このシナリオを削除しますか？")) return;
      post("/scenarios/" + id + "/delete/").then(function () {
        location.reload(); // 論理削除してから一覧を再表示する
      }).catch(function (err) {
        window.Kataru.toast(err.message, "error");
      });
    }
  });
})();
