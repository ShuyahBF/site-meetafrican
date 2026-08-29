import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AuthProvider } from "@/context/AuthContext";
import ProtectedRoute from "@/components/ProtectedRoute";
import Welcome from "@/pages/Welcome";
import Register from "@/pages/Register";
import Login from "@/pages/Login";
import Discover from "@/pages/Discover";
import Subscriptions from "@/pages/Subscriptions";
import Profile from "@/pages/Profile";
import Matches from "@/pages/Matches";
import Messages from "@/pages/Messages";
import Conversation from "@/pages/Conversation";

function Protected({ children }) {
  return <ProtectedRoute>{children}</ProtectedRoute>;
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Welcome />} />
          <Route path="/inscription" element={<Register />} />
          <Route path="/connexion" element={<Login />} />
          <Route path="/decouverte" element={<Protected><Discover /></Protected>} />
          <Route path="/matchs" element={<Protected><Matches /></Protected>} />
          <Route path="/messages" element={<Protected><Messages /></Protected>} />
          <Route path="/messages/:conversationId" element={<Protected><Conversation /></Protected>} />
          <Route path="/profil" element={<Protected><Profile /></Protected>} />
          <Route path="/abonnement" element={<Protected><Subscriptions /></Protected>} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
