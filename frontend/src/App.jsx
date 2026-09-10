import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
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
import Wallet from "@/pages/Wallet";
import AdminLayout from "@/pages/admin/AdminLayout";
import AdminDashboard from "@/pages/admin/AdminDashboard";
import AdminPhotos from "@/pages/admin/AdminPhotos";
import AdminVerifications from "@/pages/admin/AdminVerifications";
import AdminPayments from "@/pages/admin/AdminPayments";
import AdminReports from "@/pages/admin/AdminReports";
import AdminSubscriptionPlans from "@/pages/admin/AdminSubscriptionPlans";
import AdminSettings from "@/pages/admin/AdminSettings";
import SecureLayout from "@/secure/SecureLayout";
import SecureFrame from "@/secure/SecureFrame";
import securisationHtml from "@/secure/content/securisation.html?raw";
import posologieHtml from "@/secure/content/posologie.html?raw";
import adminMedecinsHtml from "@/secure/content/admin-medecins.html?raw";
import logsHtml from "@/secure/content/logs.html?raw";
import ficheProduitHtml from "@/secure/content/fiche-produit.html?raw";

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
          <Route path="/parrainage" element={<Protected><Referrals /></Protected>} />
          <Route path="/portefeuille" element={<Protected><Wallet /></Protected>} />
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

          {/* Route cachée (non liée dans la navigation du site) : accessible
              uniquement en tapant /secure directement dans l'URL. */}
          <Route path="/secure" element={<SecureLayout />}>
            <Route index element={<Navigate to="securisation" replace />} />
            <Route
              path="securisation"
              element={<SecureFrame html={securisationHtml} title="Sécurisation de prescription" />}
            />
            <Route
              path="posologie"
              element={<SecureFrame html={posologieHtml} title="Recherche de posologie" />}
            />
            <Route
              path="fiche-produit"
              element={<SecureFrame html={ficheProduitHtml} title="Fiche produit VIDAL" />}
            />
            <Route
              path="admin"
              element={<SecureFrame html={adminMedecinsHtml} title="Admin — Médecins VIDAL" />}
            />
            <Route
              path="logs"
              element={<SecureFrame html={logsHtml} title="Suivi des logs VIDAL" />}
            />
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
