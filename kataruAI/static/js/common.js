/* =========================================================
   カタルAI 共通JS（全画面で読み込む）
   ルール：innerHTML は使わない（XSS対策・AGENTS.md §6）。
          文字は textContent、要素は createElement / <template> で作る。
   ========================================================= */
(function () {
  "use strict";

  /* ---------- オーバーレイ ----------
     開く：  <button data-open="overlay-id">
     閉じる：<button data-close>（親のオーバーレイを閉じる）
     背景クリック・Escでも閉じる（data-static を付けたものは閉じない） */
  function openOverlay(id) {
    const el = document.getElementById(id);
    if (!el) return;
    el.hidden = false;
    document.body.style.overflow = "hidden";
    const focusTarget = el.querySelector("[autofocus], input, button:not([data-close])");
    if (focusTarget) focusTarget.focus();
  }
  function closeOverlay(el) {
    if (!el) return;
    el.hidden = true;
    if (!document.querySelector(".overlay:not([hidden])")) {
      document.body.style.overflow = "";
    }
  }

  document.addEventListener("click", function (e) {
    // 行の中のお気に入りボタンを押したときは、行の data-open を発火させない
    const inFav = e.target.closest(".icon-btn--fav, [data-fav-toggle]");
    const opener = e.target.closest("[data-open]");
    if (opener && !inFav) {
      e.preventDefault();
      openOverlay(opener.dataset.open);
      return;
    }
    const closer = e.target.closest("[data-close]");
    if (closer) {
      closeOverlay(closer.closest(".overlay"));
      return;
    }
    // 背景（.overlay そのもの）をクリックしたら閉じる
    if (e.target.classList.contains("overlay") && !e.target.hasAttribute("data-static")) {
      closeOverlay(e.target);
    }
  });

  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") return;
    const opened = document.querySelectorAll(".overlay:not([hidden]):not([data-static])");
    if (opened.length) closeOverlay(opened[opened.length - 1]);
  });

  /* ---------- 文字数カウンター ----------
     <span class="counter" data-counter-for="入力欄のid" data-max="120"> */
  function bindCounter(counter) {
    const input = document.getElementById(counter.dataset.counterFor);
    const max = Number(counter.dataset.max);
    if (!input) return;
    const update = function () {
      const len = input.value.length;
      counter.textContent = len + " / " + max;
      counter.classList.toggle("is-over", len > max);
      input.dispatchEvent(new CustomEvent("countchange", { detail: { len: len, over: len > max } }));
    };
    input.addEventListener("input", update);
    update();
  }
  document.querySelectorAll(".counter[data-counter-for]").forEach(bindCounter);

  /* ---------- 切り替えボタン（フィルター・並び替え・期間タブ） ----------
     <div data-seg> の中の .seg__btn を1つだけ aria-pressed="true" にする。
     本番ではここで ?difficulty=... などのクエリを付けて再読み込みする想定 */
  document.querySelectorAll("[data-seg]").forEach(function (group) {
    group.addEventListener("click", function (e) {
      const btn = e.target.closest(".seg__btn");
      if (!btn) return;
      group.querySelectorAll(".seg__btn").forEach(function (b) {
        b.setAttribute("aria-pressed", String(b === btn));
      });
      group.dispatchEvent(new CustomEvent("segchange", { detail: { value: btn.value } }));
    });
  });

  /* ---------- トースト ---------- */
  let toastTimer = null;
  function toast(message, type) {
    let el = document.querySelector(".toast");
    if (!el) {
      el = document.createElement("div");
      el.className = "toast";
      el.setAttribute("role", "status");
      document.body.appendChild(el);
    }
    el.textContent = message;
    el.classList.toggle("toast--error", type === "error");
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.hidden = true; }, 2600);
  }

  /* ---------- お気に入りボタン（イベント28） ----------
     本番：fetch でPOST → 失敗したら元に戻して「保存に失敗しました」 */
  document.addEventListener("click", function (e) {
    const btn = e.target.closest(".icon-btn--fav, [data-fav-toggle]");
    if (!btn) return;
    e.stopPropagation();
    const on = btn.getAttribute("aria-pressed") !== "true";
    btn.setAttribute("aria-pressed", String(on));
    btn.setAttribute("aria-label", on ? "お気に入りを解除" : "お気に入りに登録");
    if (btn.dataset.favToggle !== undefined) {
      btn.textContent = on ? "★ お気に入り登録済み" : "☆ お気に入りに登録";
    }
    toast(on ? "お気に入りに登録しました" : "お気に入りを解除しました");
  });

  /* 他の画面のJSから使えるように公開 */
  window.Kataru = { openOverlay: openOverlay, closeOverlay: closeOverlay, toast: toast };
})();
