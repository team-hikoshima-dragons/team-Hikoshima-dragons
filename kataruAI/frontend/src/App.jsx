import { useState, useRef, useEffect } from 'react'
import './App.css'
import ChatBox from './components/ChatBox.jsx'

export default function App() {
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
        if (!text || loading) return

        // 自分の発言を履歴に足して、入力欄を空にする
        const newMessages = [...messages, { role: 'user', text }]
        setMessages(newMessages)
        setInput('')
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

    return (
        <div className="chat">
        <h1>Gemini チャットボット</h1>

        <div className="messages">
            {messages.map((m, i) => (
            <div key={i} className={'bubble ' + m.role}>
                {m.text}
            </div>
            ))}
            {loading && <div className="bubble model">考え中…</div>}
            <div ref={bottomRef} />
        </div>

        <div className="input-area">
            <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="メッセージを入力(Enterで送信、Shift+Enterで改行)"
            rows={2}
            />
            <button onClick={sendMessage} disabled={loading}>
            送信
            </button>
        </div>
        </div>
    )
}