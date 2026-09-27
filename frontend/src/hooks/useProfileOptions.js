import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api";

// Listes fermées (centres d'intérêt, types de relation, enfants) servies
// par GET /profile-options — mises en cache pour toute la session.
let cache = null;

export function useProfileOptions() {
  const [options, setOptions] = useState(cache);
  useEffect(() => {
    if (cache) return;
    apiClient.get("/profile-options").then((r) => {
      cache = r.data;
      setOptions(r.data);
    });
  }, []);
  return options;
}
