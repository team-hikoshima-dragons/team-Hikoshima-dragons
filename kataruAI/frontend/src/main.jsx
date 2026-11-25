import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import ChatBox from './ChatBox.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <ChatBox />
  </StrictMode>,
)