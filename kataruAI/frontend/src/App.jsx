// React Router から必要な道具を取り寄せる
import { BrowserRouter, Routes, Route, Link } from "react-router-dom";
import ChatBox from './components/ChatBox';
import './App.css';

export default function App() {
    return (
        <BrowserRouter>
            <div className="app-container">
                {/* ホーム画面のヘッダーやナビゲーションを置くスペース */}
                <header className="app-header">
                    <h1>マイアプリ ホーム</h1>
                </header>
                <nav
                    style={{
                        display: "flex",
                        gap: "16px",
                        padding: "12px",
                        backgroundColor: "#eee",
                        borderRadius: "8px",
                        marginBottom: "24px",
                    }}
                >
                    <Link to="/">ホーム</Link>
                    <Link to="/chatbox">チャットホーム</Link>
                </nav>

                {/* ④ URLに合わせて画面を切り替えるエリア */}
                <Routes>
                    {/* ① URLが「/」（最初の画面）のときの表示 */}
                    <Route 
                        path="/" 
                        element={
                            <div style={{ textAlign: "center", marginTop: "40px" }}>
                                <h2>AIチャットアプリへようこそ！</h2>
                                <p>下のボタン、または上のメニューからチャット画面へ進んでください。</p>
                                <Link to="/chatbox">
                                    <button 
                                        style={{ 
                                            padding: "12px 24px", 
                                            fontSize: "16px", 
                                            backgroundColor: "#007bff", 
                                            color: "white", 
                                            border: "none", 
                                            borderRadius: "6px", 
                                            cursor: "pointer",
                                            marginTop: "16px" 
                                        }}
                                    >
                                        チャットを始める 🚀
                                    </button>
                                </Link>
                            </div>
                        } 
                    />

                    {/* ② URLが「/chatbox」のときに ChatBox を表示 */}
                    <Route path="/chatbox" element={<ChatBox />} />
                </Routes>
            </div>
        </BrowserRouter>
    );
}