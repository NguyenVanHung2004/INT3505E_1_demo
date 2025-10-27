import { NextResponse } from "next/server";
import { api, setAccessToken } from "@/lib/api";

export async function POST() {
  try { await api.post("/auth/logout"); } catch {}
  setAccessToken(null);
  return NextResponse.redirect(new URL("/login", process.env.NEXT_PUBLIC_BASE_URL || "http://localhost:3000"));
}
