import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AuthProvider } from "@/context/AuthContext";
import ProtectedRoute from "@/components/ProtectedRoute";
import Welcome from "@/pages/Welcome";
import Register from "@/pages/Register";
import Login from "@/pages/Login";
import Discover from "@/pages/Discover";
import Subscriptions from "@/pages/Subscriptions";

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Welcome />} />
          <Route path="/inscription" element={<Register />} />
          <Route path="/connexion" element={<Login />} />
          <Route
            path="/decouverte"
            element={
              <ProtectedRoute>
                <Discover />
              </ProtectedRoute>
            }
          />
          <Route
            path="/abonnement"
            element={
              <ProtectedRoute>
                <Subscriptions />
              </ProtectedRoute>
            }
          />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
