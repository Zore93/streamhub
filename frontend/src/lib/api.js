import axios from "axios";

export const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

const api = axios.create({ baseURL: API });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export const mediaUrl = (rel) => {
  if (!rel) return "";
  if (rel.startsWith("http")) return rel;
  return `${API}/media/${rel.replace(/^\//, "")}`;
};

export default api;
