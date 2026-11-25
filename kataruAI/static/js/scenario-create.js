/* シナリオ作成（イベント39〜42）
   ※事前チェックは使いやすさのため。サーバー側（scenarios/forms.py）でも同じ検証をしている。
   送信：POST /scenarios/create/（multipart/form-data・X-CSRFToken）。失敗しても入力内容は消さない。 */
(function () {
  "use strict";

  const $ = function (id) { return document.getElementById(id); };
  const form = $("create-form");
  const title = $("title");
  const desc = $("description");
  const formError = $("form-error");
  const MAX_IMG = 2 * 1024 * 1024;
  const IMG_TYPES = ["image/png", "image/jpeg", "image/webp"];
  let objectUrl = null;

  // タイトル入力をプレビューに反映（No.23）
  title.addEventListener("input", function () {
    const el = $("preview-title");
    el.textContent = title.value.trim() || "タイトル";
    el.classList.toggle("placeholder-text", !title.value.trim());
  });

  /* ---------- 画像の検証とプレビュー（イベント39） ---------- */
  $("character_image").addEventListener("change", function (e) {
    const input = e.target;
    const file = input.files[0];
    const err = $("img-error");
    err.hidden = true;
    if (!file) return;
    if (IMG_TYPES.indexOf(file.type) === -1 || file.size > MAX_IMG) {
      err.textContent = "PNG・JPEG・WebPで、2MB以内の画像を選んでね。";
      err.hidden = false;
      input.value = ""; // 選択を取り消す
      return;
    }
    if (objectUrl) URL.revokeObjectURL(objectUrl);
    objectUrl = URL.createObjectURL(file);
    $("img-preview").src = objectUrl;
    $("preview-img").src = objectUrl;
  });

  /* ---------- 入力ヒント（イベント40） ---------- */
  document.querySelectorAll(".hint-chip").forEach(function (chip) {
    chip.addEventListener("click", function () {
      const add = (desc.value && !desc.value.endsWith("\n") ? "\n" : "") + chip.dataset.hint;
      if ((desc.value + add).length > 400) return; // 400文字を超えるなら追記しない
      desc.value += add;
      desc.dispatchEvent(new Event("input")); // 文字数表示を更新
      desc.focus();
      desc.setSelectionRange(desc.value.length, desc.value.length);
    });
  });

  /* ---------- キャンセル（イベント42） ---------- */
  $("cancel-link").addEventListener("click", function (e) {
    const dirty = title.value || desc.value || $("character_image").value;
    if (dirty && !confirm("入力内容を破棄しますか？")) e.preventDefault();
  });

  /* ---------- 作成（イベント41） ---------- */
  function showError(text, input) {
    formError.textContent = text;
    formError.hidden = false;
    if (input) { input.classList.add("is-error"); input.focus(); }
  }

  function setPreview(id, text) {
    const el = $(id);
    el.textContent = text;
    el.classList.remove("placeholder-text");
  }

  /* ---------- 再保存（ユースケース記述 ⑥-a） ---------- */
  let resaveToken = "";
  function hideResave() {
    resaveToken = "";
    $("resave-area").hidden = true;
  }
  $("resave-btn").addEventListener("click", function () {
    if (!resaveToken) return;
    formError.hidden = true;
    send(resaveToken);
  });

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    hideResave(); // 作成し直すときは、前の一時保存は使わない
    formError.hidden = true;
    form.querySelectorAll(".is-error").forEach(function (el) { el.classList.remove("is-error"); });

    const t = title.value.trim();
    const d = desc.value.trim();
    if (!t || t.length > 40) return showError("タイトルは1〜40文字で入力してね。", title);
    if (!form.querySelector('input[name="difficulty"]:checked')) return showError("難易度を選んでね。");
    if (!d || d.length > 400) return showError("説明は1〜400文字で入力してね。", desc);
    send("");
  });

  // resave：再保存の番号（空なら AI で生成して作成する）
  function send(resave) {
    const btn = $("generate-btn");
    btn.disabled = true;
    btn.textContent = "作成中…";
    $("preview-loading").hidden = false;
    $("preview-body").hidden = true;

    const csrf = form.querySelector('input[name="csrfmiddlewaretoken"]').value;
    function done() {
      btn.disabled = false;
      btn.textContent = "AIでシナリオを作成";
      $("preview-loading").hidden = true;
      $("preview-body").hidden = false;
    }

    const body = new FormData(form);
    if (resave) body.append("resave", resave);
    $("resave-btn").disabled = true;

    fetch(location.pathname, {
      method: "POST",
      credentials: "same-origin",
      headers: { "X-CSRFToken": csrf },
      body: body,
      signal: AbortSignal.timeout(45000) // サーバー側の Gemini 待ち（25秒）より長めに待つ
    })
      .then(function (res) {
        return res.json().catch(function () { return null; }).then(function (data) {
          done();
          $("resave-btn").disabled = false;
          if (!res.ok || !data) {
            const message = data && data.error && data.error.message;
            // DB 保存の失敗だけ「再保存」ボタンを出す（それ以外は出さない）
            if (data && data.resave_token) {
              resaveToken = data.resave_token;
              $("resave-area").hidden = false;
            } else {
              hideResave();
            }
            return showError(message || "シナリオの作成に失敗しました。もう一度ためしてね。");
          }
          hideResave();
          setPreview("preview-name", data.character_name);
          setPreview("preview-intro", data.character_intro);
          setPreview("preview-goal", data.goal);
          setPreview("preview-cond", data.condition);
          window.Kataru.toast("シナリオを作成しました（非公開・共有コード：" + data.share_code + "）");
        });
      })
      .catch(function () {
        done();
        $("resave-btn").disabled = false;
        showError("通信エラーが発生しました。もう一度ためしてね。");
      });
  }
})();
