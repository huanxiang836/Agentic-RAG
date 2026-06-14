import { Navigate, Route, Routes } from "react-router-dom";

import { ChatWorkspacePage } from "./pages/ChatWorkspacePage";

export function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/chat/new" replace />} />
      <Route path="/chat/:conversationId" element={<ChatWorkspacePage />} />
    </Routes>
  );
}
