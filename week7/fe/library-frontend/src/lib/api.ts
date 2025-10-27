import axios from "axios";

export const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_BASE,
  withCredentials: true, // gửi cookie refresh
});

// access token giữ trong module memory (không LocalStorage để tránh XSS)
let accessToken: string | null = null;
export const setAccessToken = (t: string | null) => { accessToken = t; };
export const getAccessToken = () => accessToken;

api.interceptors.request.use((config) => {
  if (accessToken) config.headers.Authorization = `Bearer ${accessToken}`;
  return config;
});

let refreshing = false;
let waiters: Array<() => void> = [];

api.interceptors.response.use(
  r => r,
  async (error) => {
    const original = error.config;
    const status = error?.response?.status;
    if (status === 401 && !original._retry) {
      if (refreshing) {
        await new Promise<void>(res => waiters.push(res));
      } else {
        refreshing = true;
        original._retry = true;
        try {
          const res = await api.post("/auth/refresh"); // cookie refresh tự gửi
          setAccessToken(res.data.access_token);
          waiters.forEach(fn => fn());
        } catch (e) {
          setAccessToken(null);
          waiters.forEach(fn => fn());
          throw e;
        } finally {
          refreshing = false;
          waiters = [];
        }
      }
      return api(original);
    }
    throw error;
  }
);
