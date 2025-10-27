"use client";
import { useState } from "react";
import { api, setAccessToken } from "@/lib/api";
import { useRouter } from "next/navigation";

export default function LoginPage() {
  const [email, setEmail] = useState("admin@example.com");
  const [password, setPassword] = useState("Admin@123");
  const [err, setErr] = useState<string | null>(null);
  const router = useRouter();

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    try {
      const res = await api.post("/auth/login", { email, password });
      setAccessToken(res.data.access_token);
      router.push("/books");
    } catch (e: any) {
      setErr(e?.response?.data?.message || "Login failed");
    }
  }

  return (
    <div className="max-w-sm mx-auto bg-white p-6 rounded-2xl border shadow">
      <h1 className="text-lg font-semibold mb-4">Đăng nhập</h1>
      <form onSubmit={onSubmit} className="space-y-3">
        <div>
          <label className="text-sm">Email</label>
          <input className="w-full border rounded px-3 py-2" value={email} onChange={e=>setEmail(e.target.value)} />
        </div>
        <div>
          <label className="text-sm">Mật khẩu</label>
          <input type="password" className="w-full border rounded px-3 py-2" value={password} onChange={e=>setPassword(e.target.value)} />
        </div>
        {err && <p className="text-sm text-red-600">{err}</p>}
        <button className="w-full bg-black text-white rounded py-2">Login</button>
      </form>
    </div>
  );
}
