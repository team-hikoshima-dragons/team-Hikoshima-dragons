import { useState, useRef, useEffect } from 'react'

// =====================================================================
// プレイ画面。見た目（HTML の構造と class 名）は、元の ChatBox.jsx のまま。
// 変えたのは中身だけ：
//   ・お題／キャラ／ゴール／残りターンは、サーバー（/api/plays/{id}/）から受け取る
//   ・発言は POST /api/plays/{id}/turns/ に送る（返答・様子・表情・残りターンが返る）
//   ・機嫌・疑い・理解度の数値は、サーバーが返さないので、この画面は一切知らない
// CSSは Django の static（common.css / play.css）を使う。ここでは import しない。
// =====================================================================

// ---------- API 呼び出しの共通処理 ----------

// Django が配る csrftoken の Cookie を読む。
// POST するときに X-CSRFToken ヘッダーで送る（AGENTS.md §6：@csrf_exempt は使わない）
function getCookie(name) {
    const prefix = name + '='
    const found = document.cookie.split('; ').find((row) => row.startsWith(prefix))
    return found ? decodeURIComponent(found.slice(prefix.length)) : ''
}

// APIを呼んで { ok, data } を返す。
// 通信そのものが失敗したとき（サーバー停止・タイムアウト）は ok:false, data:null
async function apiRequest(method, url, body) {
    try {
        const res = await fetch(url, {
            method,
            credentials: 'same-origin',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken'),
            },
            body: body === undefined ? undefined : JSON.stringify(body),
            // サーバー側のGemini待ち（25秒）より少し長めに待つ
            signal: AbortSignal.timeout(45000),
        })
        // JSON以外が返ってきたとき（Djangoのエラーページなど）でも落ちないようにする
        const data = await res.json().catch(() => null)
        return { ok: res.ok, data }
    } catch {
        return { ok: false, data: null }
    }
}

// URL（/plays/<プレイID>/）からプレイIDを取り出す。無ければ空文字
function getPlayIdFromUrl() {
    const parts = window.location.pathname.split('/').filter(Boolean) // ['plays', '<id>']
    return parts[0] === 'plays' && parts[1] ? parts[1] : ''
}

const MAX_LENGTH = 120 // 発言の上限（サーバー側でも検証している）
const AVATAR_INITIAL = 'K' // TODO：会員のときは頭文字、ゲストのときの表示を決める（元のコードのまま）

// 表情の画像は Django の static から配る
const faceSrc = (expression) => `/static/img/face-${expression}.svg`

export default function ChatBox() {
    const [playId] = useState(getPlayIdFromUrl) // 開いたときのURLから読む

    // ---- サーバーから受け取った内容 ----
    // play: お題・キャラ・ゴール・条件・ターン上限など（最初の読み込み）
    const [play, setPlay] = useState(null)
    // messages: 会話の履歴 [{ role: 'user' か 'model', text: '本文' }, ...]
    const [messages, setMessages] = useState([])
    const [stateText, setStateText] = useState('') // 「いまの様子」
    const [expression, setExpression] = useState('normal') // 表情
    const [turnsLeft, setTurnsLeft] = useState(0) // 残りターン
    const [status, setStatus] = useState('playing') // playing / cleared（失敗はリザルトへ移動）
    const [resultUrl, setResultUrl] = useState('') // クリア後の「結果を見る」の行き先

    // ---- 画面の状態 ----
    const [loadError, setLoadError] = useState(!playId) // プレイが読み込めない（IDなし含む）
    // input: 入力欄に今書いている文字
    const [input, setInput] = useState('')
    // loading: 返事待ちかどうか
    const [loading, setLoading] = useState(false)
    const [showError, setShowError] = useState(false) // 通信エラー（再試行ボタンを出す）
    const [notice, setNotice] = useState('') // ブロックなどのお知らせ
    const lastMessage = useRef('') // 再試行で送り直す発言
    // 一番下の目印(自動スクロール用)
    const bottomRef = useRef(null)

    // 会話が増えたら、一番下までスクロールする
    useEffect(() => {
        if (bottomRef.current) {
            bottomRef.current.scrollIntoView({ behavior: 'smooth' })
        }
    }, [messages, loading, notice])

    // サーバーから受け取った「プレイの状態」を画面に反映する。
    // 読み込み時・ターンのずれ・終了済みの検知で共通して使う。
    const applyPlay = (view) => {
        setPlay(view)
        setMessages(view.messages)
        setStateText(view.state)
        setExpression(view.expression)
        setTurnsLeft(view.turns_left)
        setStatus(view.status)
        setResultUrl(view.result_url || '')
        // 失敗済みならリザルトへ、中断済みならトップへ移動する
        if (view.status === 'failed' && view.result_url) window.location.href = view.result_url
        if (view.status === 'aborted') window.location.href = '/'
    }

    // 最初にプレイの状態を取得する（リロード時も同じ）
    useEffect(() => {
        if (!playId) return
        let cancelled = false
        apiRequest('GET', `/api/plays/${playId}/`).then(({ ok, data }) => {
            if (cancelled) return
            if (!ok || !data) setLoadError(true)
            else applyPlay(data)
        })
        return () => {
            cancelled = true
        }
    }, [playId])

    // 送信できる条件：返事待ちでなく、空でなく、120文字以内で、プレイ中
    const canSend =
        !loading && status === 'playing' && input.trim() !== '' && input.length <= MAX_LENGTH

    // 発言を送る。addBubble=false は再試行（吹き出しは既にあるので足さない）
    const send = async (text, addBubble) => {
        setLoading(true)
        setShowError(false)
        setNotice('')
        if (addBubble) setMessages((prev) => [...prev, { role: 'user', text }])

        // 今回が何ターン目か（使用ターン＋1）。サーバーが「ずれ」を検出するのに使う
        const turnNo = play.turn_limit - turnsLeft + 1
        const { ok, data } = await apiRequest('POST', `/api/plays/${playId}/turns/`, {
            text,
            turn_no: turnNo,
        })
        setLoading(false)

        // ---- 成功 ----
        if (ok && data) {
            setMessages((prev) => [...prev, { role: 'model', text: data.reply }])
            setStateText(data.state)
            setExpression(data.expression)
            setTurnsLeft(data.turns_left)
            setStatus(data.status)
            if (data.status === 'cleared') setResultUrl(data.result_url)
            if (data.status === 'failed') window.location.href = data.result_url // 失敗はリザルトへ
            return
        }

        // ---- 失敗：エラーコードごとに表示を変える ----
        const code = data && data.error && data.error.code
        if (code === 'BLOCKED' || code === 'BAD_REQUEST') {
            setNotice(data.error.message) // ターンは消費されていない
        } else if (code === 'TURN_MISMATCH' && data.play) {
            applyPlay(data.play) // ずれていたので、サーバーの最新の状態に合わせる
        } else if (code === 'NOT_PLAYING') {
            const reloaded = await apiRequest('GET', `/api/plays/${playId}/`)
            if (reloaded.ok && reloaded.data) applyPlay(reloaded.data)
        } else {
            setShowError(true) // 通信エラー・AIエラー：再試行ボタンを出す
        }
    }

    // 送信ボタンを押したときの処理
    const sendMessage = () => {
        if (!canSend) return
        const text = input.trim()
        lastMessage.current = text
        setInput('')
        send(text, true)
    }

    // Enterで送信、Shift+Enterで改行
    const handleKeyDown = (e) => {
        // 日本語変換中のEnter(確定)では送信しない
        if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault()
            sendMessage()
        }
    }

    // あきらめる：確認 → サーバーで失敗（0点）にしてリザルトへ
    const handleGiveUp = async () => {
        if (!window.confirm('あきらめますか？')) return
        const { ok, data } = await apiRequest('POST', `/api/plays/${playId}/give-up/`)
        if (ok && data) window.location.href = data.result_url
        else setShowError(true)
    }

    // ロゴを押したとき：プレイ中なら確認して中断する。クリア後はそのまま戻る
    const handleLogo = async (e) => {
        if (status !== 'playing') return
        e.preventDefault()
        if (!window.confirm('プレイを中断しますか？')) return
        const { data } = await apiRequest('POST', `/api/plays/${playId}/abort/`)
        window.location.href = (data && data.redirect_url) || '/'
    }

    // ---- 読み込めなかったとき・読み込み中 ----
    if (loadError) {
        return (
            <div className="page">
                <main className="main main--center">
                    <div className="container container--narrow">
                        <div className="card" style={{ textAlign: 'center' }}>
                            <p className="modal__title">プレイが見つかりませんでした</p>
                            <p className="modal__text">
                                トップの「ゲストで遊ぶ」から始めてください。
                            </p>
                            <div className="modal__actions">
                                <a className="btn btn--primary" href="/">トップへ</a>
                            </div>
                        </div>
                    </div>
                </main>
            </div>
        )
    }
    if (!play) {
        return (
            <div className="page">
                <main className="main main--center">
                    <div className="spinner" aria-label="読み込み中" />
                </main>
            </div>
        )
    }

    const name = play.character.name
    // 最後のAIの発言の位置（そこだけ今の表情にして、ほかは普通の顔にする）
    const lastModelIndex = messages.map((m) => m.role).lastIndexOf('model')

    return (
        <div className="play-page">
            <header className="play-header">
                <a href="/" className="logo" onClick={handleLogo}>カタル<span>AI</span></a>
                <div className="play-header__theme">
                    <span className="tag-ink">お題</span>
                    <p>{play.title}</p>
                </div>
                <div className={'turns' + (turnsLeft <= 3 ? ' is-low' : '')}>
                    残り<span className="turns__num">{turnsLeft}</span>/ <span>{play.turn_limit}</span>ターン
                </div>
                {status === 'playing' && (
                    <button type="button" className="btn-text btn-text--danger" onClick={handleGiveUp}>
                        あきらめる
                    </button>
                )}
            </header>

            <div className="play-main">
                <aside className="opp">
                    <div className="opp__profile">
                        <div className="opp__face" data-mood={expression}>
                            <img src={faceSrc(expression)} alt={`${name}の表情`} width="150" height="150" />
                        </div>
                        <h2 className="opp__name">{name}</h2>
                        <p className="opp__desc">{play.character.intro}</p>
                    </div>
                    <div className="mood">
                        <p className="mood__label">いまの様子</p>
                        <p className="mood__text">{stateText}</p>
                    </div>
                    <div className="goal">
                        <p className="goal__item"><span className="tag-ink">ゴール</span><span>{play.goal}</span></p>
                        <p className="goal__item"><span className="tag-ink">条件</span><span>{play.condition}</span></p>
                    </div>
                    <p className="opp__note">機嫌・疑い・理解度は数字では見えません。表情と様子から読み取ろう。</p>
                </aside>

                <section className="conv">
                    <div className="conv__log">
                        <div className="talk">
                            {messages.map((m, i) =>
                                m.role === 'user' ? (
                                    <div key={i} className="talk__row talk__row--user">
                                        <p className="talk__bubble">{m.text}</p>
                                        <span className="avatar">{AVATAR_INITIAL}</span>
                                    </div>
                                ) : (
                                    <div key={i} className="talk__row talk__row--opp">
                                        <span className="talk__icon">
                                            <img src={faceSrc(i === lastModelIndex ? expression : 'normal')} alt="" />
                                        </span>
                                        <p className="talk__bubble">{m.text}</p>
                                    </div>
                                )
                            )}
                            {loading && <p className="talk__typing">{name}が考えています</p>}
                            {notice && <p className="talk__notice">{notice}</p>}
                            <div ref={bottomRef} />
                        </div>
                    </div>

                    <div className="composer-box">
                        {/* 通信エラー：再試行 or キャンセル */}
                        {showError && (
                            <div className="composer-box__error">
                                <p className="alert alert--error">通信エラーが発生しました</p>
                                <div>
                                    <button type="button" className="btn btn--s" onClick={() => setShowError(false)}>
                                        キャンセル
                                    </button>{' '}
                                    <button
                                        type="button"
                                        className="btn btn--s btn--primary"
                                        disabled={loading}
                                        onClick={() => send(lastMessage.current, false)}
                                    >
                                        再試行
                                    </button>
                                </div>
                            </div>
                        )}

                        {status === 'cleared' ? (
                            // クリア：入力欄の代わりに「結果を見る」を出す
                            <div className="composer-box__goal">
                                <span>🎉 ゴール達成！</span>
                                <a className="btn btn--primary" href={resultUrl}>結果を見る</a>
                            </div>
                        ) : (
                            <>
                                <div className="composer-box__row">
                                    <textarea
                                        className="textarea"
                                        value={input}
                                        onChange={(e) => setInput(e.target.value)}
                                        onKeyDown={handleKeyDown}
                                        placeholder={`${name}に話しかけよう（${MAX_LENGTH}文字まで）`}
                                    />
                                    <button type="button" className="btn btn--primary" onClick={sendMessage} disabled={!canSend}>
                                        送信
                                    </button>
                                </div>
                                <div className="composer-box__foot">
                                    <span>1回の発言で1ターン消費します</span>
                                    <span className={'counter' + (input.length > MAX_LENGTH ? ' is-over' : '')}>
                                        {input.length} / {MAX_LENGTH}
                                    </span>
                                </div>
                            </>
                        )}
                    </div>
                </section>
            </div>
        </div>
    )
}
