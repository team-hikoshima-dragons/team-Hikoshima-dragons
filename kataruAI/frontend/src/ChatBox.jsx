import { useState, useRef, useEffect } from 'react'
import './App.css'      // CSS が src/ 直下にある場合

export default function ChatBox() {
    // messages: 会話の履歴 [{ role: 'user' か 'model', text: '本文' }, ...]
    const [messages, setMessages] = useState([])
    // input: 入力欄に今書いている文字
    const [input, setInput] = useState('')
    // loading: 返事待ちかどうか
    const [loading, setLoading] = useState(false)
    // 一番下の目印(自動スクロール用)
    const bottomRef = useRef(null)

    // 会話が増えたら、一番下までスクロールする
    useEffect(() => {
        if (bottomRef.current) {
        bottomRef.current.scrollIntoView({ behavior: 'smooth' })
        }
    }, [messages, loading])

    // 送信ボタンを押したときの処理
    const sendMessage = async () => {
        const text = input.trim()
        if (!text || loading || turnsLeft <= 0) return

        // 自分の発言を履歴に足して、入力欄を空にする
        const newMessages = [...messages, { role: 'user', text }]
        setMessages(newMessages)
        setInput('')
        setTurnsLeft((n) => n - 1)   // ← 追加：発言ごとに1消費
        setLoading(true)

        try {
        // Django に会話履歴を送る
        const res = await fetch('/plays/chat/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            // エラー表示は会話ではないので、Geminiには送らない
            body: JSON.stringify({ messages: newMessages.filter((m) => !m.isError) }),
        })
        // Djangoが止まっているときなどは、JSON以外の応答が返ることがある
        const data = await res.json().catch(() => null)
        if (!data) {
            throw new Error(`サーバーから正しい応答がありません(${res.status})。Djangoが起動しているか確認してください`)
        }
        if (!res.ok) throw new Error(data.error || 'エラーが発生しました')

        // 返事を履歴に足す
        setMessages([...newMessages, { role: 'model', text: data.reply }])
        } catch (err) {
        setMessages([...newMessages, { role: 'model', text: '⚠️ ' + err.message, isError: true }])
        } finally {
        setLoading(false)
        }
    }

    // Enterで送信、Shift+Enterで改行
    const handleKeyDown = (e) => {
        // 日本語変換中のEnter(確定)では送信しない
        if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
        e.preventDefault()
        sendMessage()
        }
    }

    const TURN_MAX = 15                         // 上限（今は固定。将来は難易度で変える）
    const [turnsLeft, setTurnsLeft] = useState(TURN_MAX)

    return (
        <div className="play-page">
            <header className="play-header">
            <a href="/" className="logo">カタル<span>AI</span></a>
            <div className="play-header__theme">
                <span className="tag-ink">お題</span>
                <p>頑固な喫茶店マスターに、閉店を30分延ばしてもらおう</p>
            </div>
            <div className={'turns' + (turnsLeft <= 3 ? ' is-low' : '')}>
                残り<span className="turns__num">15</span>/ <span>15</span>ターン
            </div>
            <button type="button" className="btn-text btn-text--danger">あきらめる</button>
            </header>

            <div className="play-main">
            <aside className="opp">
                <div className="opp__profile">
                <div className="opp__face" data-mood="normal">
                    <img src="/static/img/face-normal.svg" alt="喫茶店マスターの表情" width="150" height="150" />
                </div>
                <h2 className="opp__name">喫茶店マスター</h2>
                <p className="opp__desc">開店30年。常連は大切にするが、理屈っぽい客は嫌い。</p>
                </div>
                <div className="mood">
                <p className="mood__label">いまの様子</p>
                <p className="mood__text">警戒している</p>
                </div>
                <div className="goal">
                <p className="goal__item"><span className="tag-ink">ゴール</span><span>閉店を30分延ばすと約束させる</span></p>
                <p className="goal__item"><span className="tag-ink">条件</span><span>値引きの話はNG</span></p>
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
                        <span className="avatar">K</span>
                        </div>
                    ) : (
                        <div key={i} className="talk__row talk__row--opp">
                        <span className="talk__icon"><img src="/static/img/face-normal.svg" alt="" /></span>
                        <p className="talk__bubble">{m.text}</p>
                        </div>
                    )
                    )}
                    {loading && <p className="talk__typing">喫茶店マスターが考えています</p>}
                    <div ref={bottomRef} />
                </div>
                </div>

                <div className="composer-box">
                <div className="composer-box__row">
                    <textarea
                    className="textarea"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="マスターに話しかけよう（120文字まで）"
                    />
                    <button type="button" className="btn btn--primary" onClick={sendMessage} disabled={loading || !input.trim() || turnsLeft <= 0}>
                    送信
                    </button>
                </div>
                <div className="composer-box__foot">
                    <span>1回の発言で1ターン消費します</span>
                    <span className={'counter' + (input.length > 120 ? ' is-over' : '')}>{input.length} / 120</span>
                </div>
                </div>
            </section>
            </div>
        </div>
    )            
}