/* サインアップ：カタルンとの会話形式で入力を進める（イベント17）
   ※ここの検証は使いやすさのため。サーバー側でも同じ検証を必ずやる */
(function () {
  "use strict";

  const chat = document.getElementById("chat");
  const form = document.getElementById("composer");
  const label = document.getElementById("input-label");
  const progress = document.getElementById("progress");
  const doneArea = document.getElementById("done-area");
  const inputs = Array.from(form.querySelectorAll("[data-step]"));
  const tplBot = document.getElementById("tpl-bot");
  const tplUser = document.getElementById("tpl-user");

  const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  const TAKEN = ["taken@example.com"]; // モック用。本番はサーバーで判定

  // 各ステップの設定
  const steps = [
    {
      label: "ニックネーム",
      question: "はじめまして！ぼくはカタルン。\nまずは、きみのニックネームを教えて！（20文字まで・空欄ならランダムな名前にするよ）",
      validate: function (v) { return v.length > 20 ? "ニックネームは20文字以内にしてね。" : ""; },
      display: function (v) { return v; }
    },
    {
      label: "メールアドレス",
      question: "つぎは、メールアドレスを教えて！",
      validate: function (v) {
        if (!v) return "メールアドレスを入力してね。";
        if (!EMAIL_RE.test(v)) return "メールアドレスの形がちがうみたい。";
        if (TAKEN.indexOf(v) !== -1) return "そのメールアドレスはもう登録されてるよ。";
        return "";
      },
      display: function (v) { return v; }
    },
    {
      label: "パスワード",
      question: "パスワードを決めよう！\n8文字以上で、英字と数字を両方入れてね。",
      validate: function (v) {
        if (!v) return "パスワードを入力してね。";
        if (v.length < 8) return "パスワードは8文字以上にしてね。";
        if (!/[A-Za-z]/.test(v) || !/[0-9]/.test(v)) return "英字と数字を両方入れてね。";
        return "";
      },
      display: function (v) { return "●".repeat(v.length); }
    },
    {
      label: "パスワード(再確認)",
      question: "確認のため、もう一度パスワードを入れてね。",
      validate: function (v) {
        return v !== inputs[2].value ? "さっきのパスワードと一致しないみたい。" : "";
      },
      display: function (v) { return "●".repeat(v.length); }
    }
  ];

  let current = 0;

  function addBubble(tpl, text, isError) {
    const node = tpl.content.firstElementChild.cloneNode(true);
    node.querySelector(".msg__bubble").textContent = text; // innerHTMLは使わない
    if (isError) node.classList.add("is-error");
    chat.appendChild(node);
    chat.scrollTop = chat.scrollHeight;
  }

  function showStep(i) {
    inputs.forEach(function (input, idx) { input.hidden = idx !== i; });
    label.textContent = steps[i].label;
    label.setAttribute("for", inputs[i].id);
    progress.value = i;
    addBubble(tplBot, steps[i].question);
    inputs[i].focus();
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    const input = inputs[current];
    let value = input.value.trim();
    if (current >= 2) value = input.value; // パスワードは trim しない

    const error = steps[current].validate(value);
    if (error) {
      input.classList.add("is-error");
      addBubble(tplBot, error, true);
      return;
    }
    input.classList.remove("is-error");

    // ニックネームが空ならランダムな名前（例：プレイヤー1234）
    if (current === 0 && value === "") {
      value = "プレイヤー" + String(Math.floor(1000 + Math.random() * 9000));
      input.value = value;
    }
    addBubble(tplUser, steps[current].display(value));

    current += 1;
    if (current < steps.length) {
      showStep(current);
      return;
    }

    // 最終ステップOK → 本番はここでサーバーへPOST（fetch ＋ X-CSRFToken）
    progress.value = 4;
    form.hidden = true;
    addBubble(tplBot, "登録できたよ！さっそくログインして遊ぼう。");
    doneArea.hidden = false;
  });

  showStep(0);
})();
