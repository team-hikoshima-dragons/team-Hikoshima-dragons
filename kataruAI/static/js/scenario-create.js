/* シナリオ作成（イベント39〜42）
   ※事前チェックは使いやすさのため。サーバー側でも同じ検証が必須（画像はImageField＋UUIDファイル名） */
(function () {
  "use strict";

  const $ = function (id) { return document.getElementById(id); };
  const form = $("create-form");
  const title = $("title");
  const desc = $("description");
  const formError = $("form-error");
  const mockError = new URLSearchParams(location.search).get("mock") === "error";
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

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    formError.hidden = true;
    form.querySelectorAll(".is-error").forEach(function (el) { el.classList.remove("is-error"); });

    const t = title.value.trim();
    const d = desc.value.trim();
    if (!t || t.length > 40) return showError("タイトルは1〜40文字で入力してね。", title);
    if (!form.querySelector('input[name="difficulty"]:checked')) return showError("難易度を選んでね。");
    if (!d || d.length > 400) return showError("説明は1〜400文字で入力してね。", desc);

    const btn = $("generate-btn");
    btn.disabled = true;
    btn.textContent = "作成中…";
    $("preview-loading").hidden = false;
    $("preview-body").hidden = true;

    // ↓ 本番は fetch（multipart/form-data）。入力内容は失敗しても消さない
    setTimeout(function () {
      btn.disabled = false;
      btn.textContent = "AIでシナリオを作成";
      $("preview-loading").hidden = true;
      $("preview-body").hidden = false;

      if (d.indexOf("ブロック") !== -1) { // モック：NGワード／セーフティ
        return showError("この内容ではシナリオを作れませんでした。表現を変えてみてね。");
      }
      if (mockError) {
        return showError("シナリオの作成に失敗しました。もう一度ためしてね。");
      }
      setPreview("preview-name", "喫茶店マスター");
      setPreview("preview-intro", "開店30年。常連は大切にするが、理屈っぽい客は嫌い。最近は体力の衰えを気にしている。");
      setPreview("preview-goal", "閉店を30分延ばすと約束させる");
      setPreview("preview-cond", "値引きの話はNG");
      window.Kataru.toast("非公開で保存しました（共有コード：A1B2C3D4）");
    }, 1800);
  });
})();
