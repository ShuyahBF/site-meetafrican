import { apiClient } from "@/lib/api";

/**
 * kind="photo"    -> album profil public, renvoie { kind, url }
 * kind="document" -> pièce d'identité privée, renvoie { kind, key } (jamais d'URL)
 */
export async function uploadFile(file, kind = "photo") {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("kind", kind);
  const res = await apiClient.post("/uploads", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return res.data;
}
