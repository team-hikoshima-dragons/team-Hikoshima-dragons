/* マイページ：アカウント情報の入力チェック（イベント37）
   ※使いやすさのための事前チェック。本番の検証はDjangoのFormでやる（必須） */
(function () {
  "use strict";

  const form = document.getElementById("account-form");
  const msg = document.getElementById("form-message");
  const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  const initialEmail = form.email.value;

  function show(text, ok) {
    msg.textContent = text;
    msg.className = "alert " + (ok ? "alert--success" : "alert--error");
    msg.hidden = false;
  }

  form.addEventListener("reset", function () {
    msg.hidden = true;
    form.querySelectorAll(".is-error").forEach(function (el) { el.classList.remove("is-error"); });
  });

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    form.querySelectorAll(".is-error").forEach(function (el) { el.classList.remove("is-error"); });

    const f = form.elements;
    const name = f.username.value.trim();
    const email = f.email.value.trim();
    const cur = f.current_password.value;
    const np = f.new_password.value;
    const npc = f.new_password_confirm.value;

    function fail(input, text) { input.classList.add("is-error"); input.focus(); show(text, false); }

    if (!name || name.length > 20) return fail(f.username, "ユーザー名は1〜20文字で入力してね。");
    if (!email || !EMAIL_RE.test(email)) return fail(f.email, "メールアドレスの形がちがうみたい。");

    const changingEmail = email !== initialEmail;
    if (changingEmail || np) {
      if (!cur) return fail(f.current_password, "今のパスワードを入力してね。");
    }
    if (np) {
      if (np.length < 8) return fail(f.new_password, "新しいパスワードは8文字以上にしてね。");
      if (!/[A-Za-z]/.test(np) || !/[0-9]/.test(np)) return fail(f.new_password, "英字と数字を両方入れてね。");
      if (np !== npc) return fail(f.new_password_confirm, "確認用のパスワードが一致しないよ。");
    }

    // 本番：ここでPOST。今のパスワード不一致・メール使用中はサーバーからエラーが返る
    show("保存しました！", true);
    f.current_password.value = f.new_password.value = f.new_password_confirm.value = "";
  });
})();
