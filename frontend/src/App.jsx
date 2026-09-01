import { BrowserRouter, Route, Routes, useLocation } from "react-router-dom";
import { AuthProvider } from "@/context/AuthContext";
import ProtectedRoute from "@/components/ProtectedRoute";
import AdminRoute from "@/components/AdminRoute";
import Welcome from "@/pages/Welcome";
import Register from "@/pages/Register";
import Login from "@/pages/Login";
import Discover from "@/pages/Discover";
import Subscriptions from "@/pages/Subscriptions";
import Profile from "@/pages/Profile";
import Matches from "@/pages/Matches";
import Messages from "@/pages/Messages";
import Conversation from "@/pages/Conversation";
import Referrals from "@/pages/Referrals";
import AuthCallback from "@/pages/AuthCallback";
import AdminLayout from "@/pages/admin/AdminLayout";
import AdminDashboard from "@/pages/admin/AdminDashboard";
import AdminPhotos from "@/pages/admin/AdminPhotos";
import AdminVerifications from "@/pages/admin/AdminVerifications";
import AdminPayments from "@/pages/admin/AdminPayments";
import AdminReports from "@/pages/admin/AdminReports";
import AdminSubscriptionPlans from "@/pages/admin/AdminSubscriptionPlans";
import AdminSettings from "@/pages/admin/AdminSettings";

function Protected({ children }) {
  return <ProtectedRoute>{children}</ProtectedRoute>;
}

// Intercepte SYNCHRONEMENT (pendant le rendu, pas dans un useEffect) le
// fragment #session_id renvoyé par https://auth.emergentagent.com. Sans ça,
// ProtectedRoute pourrait rediriger vers /connexion avant que AuthCallback
// n'ait pu exécuter l'échange.
// REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
function AppRoutes() {
  const location = useLocation();
  if (location.hash?.includes("session_id=")) {
    return <AuthCallback />;
  }
  return (
    <Routes>
      <Route path="/" element={<Welcome />} />
      <Route path="/inscription" element={<Register />} />
      <Route path="/connexion" element={<Login />} />
      <Route path="/decouverte" element={<Protected><Discover /></Protected>} />
      <Route path="/matchs" element={<Protected><Matches /></Protected>} />
      <Route path="/messages" element={<Protected><Messages /></Protected>} />
      <Route path="/messages/:conversationId" element={<Protected><Conversation /></Protected>} />
      <Route path="/profil" element={<Protected><Profile /></Protected>} />
      <Route path="/parrainage" element={<Protected><Referrals /></Protected>} />
      <Route path="/abonnement" element={<Protected><Subscriptions /></Protected>} />

      <Route path="/admin" element={<AdminRoute><AdminLayout /></AdminRoute>}>
        <Route index element={<AdminDashboard />} />
        <Route path="photos" element={<AdminPhotos />} />
        <Route path="verifications" element={<AdminVerifications />} />
        <Route path="paiements" element={<AdminPayments />} />
        <Route path="signalements" element={<AdminReports />} />
        <Route path="abonnements" element={<AdminSubscriptionPlans />} />
        <Route path="parametres" element={<AdminSettings />} />
      </Route>
    </Routes>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </AuthProvider>
  );
}
