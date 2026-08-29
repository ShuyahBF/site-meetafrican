import { apiClient } from "@/lib/api";

export async function uploadFile(file) {
  const formData = new FormData();
  formData.append("file", file);
  const res = await apiClient.post("/uploads", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return res.data; // { url, filename }
}
