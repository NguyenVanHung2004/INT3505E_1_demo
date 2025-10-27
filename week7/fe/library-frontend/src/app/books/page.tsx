"use client";
import useSWR from "swr";
import { api } from "@/lib/api";
import { useState } from "react";

type Book = { id: number; title: string; author: string; stock: number };

const fetcher = (url: string) => api.get(url).then(r => r.data);

export default function BooksPage() {
  const { data, mutate, isLoading, error } = useSWR<Book[]>("/api/v1/books", fetcher);
  const [form, setForm] = useState({ title: "", author: "", stock: 0 });
  const [editId, setEditId] = useState<number | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  async function create() {
    setMsg(null);
    await api.post("/api/v1/books", { ...form, stock: Number(form.stock) });
    setForm({ title: "", author: "", stock: 0 });
    mutate();
  }
  async function update() {
    if (!editId) return;
    setMsg(null);
    await api.put(`/api/v1/books/${editId}`, { ...form, stock: Number(form.stock) });
    setEditId(null); setForm({ title: "", author: "", stock: 0 });
    mutate();
  }
  async function remove(id: number) {
    setMsg(null);
    await api.delete(`/api/v1/books/${id}`);
    mutate();
  }

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Books</h1>

      <div className="bg-white border rounded-2xl p-4 shadow space-y-3">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <input className="border rounded px-3 py-2" placeholder="Title"
            value={form.title} onChange={e=>setForm(f=>({...f, title:e.target.value}))}/>
          <input className="border rounded px-3 py-2" placeholder="Author"
            value={form.author} onChange={e=>setForm(f=>({...f, author:e.target.value}))}/>
          <input className="border rounded px-3 py-2" placeholder="Stock" type="number"
            value={form.stock} onChange={e=>setForm(f=>({...f, stock:Number(e.target.value)}))}/>
        </div>
        <div className="flex gap-3">
          {!editId ? (
            <button onClick={create} className="px-4 py-2 rounded bg-black text-white">Create</button>
          ) : (
            <button onClick={update} className="px-4 py-2 rounded bg-blue-600 text-white">Update</button>
          )}
          {editId && <button onClick={() => { setEditId(null); setForm({ title:"", author:"", stock:0 }); }} className="px-4 py-2 rounded border">Cancel</button>}
        </div>
        {msg && <p className="text-sm">{msg}</p>}
      </div>

      <div className="bg-white border rounded-2xl p-4 shadow">
        {isLoading && <p>Loading…</p>}
        {error && <p className="text-red-600">Error</p>}
        {!isLoading && !error && (
          <table className="w-full">
            <thead>
              <tr className="text-left border-b">
                <th className="py-2">ID</th><th>Title</th><th>Author</th><th>Stock</th><th></th>
              </tr>
            </thead>
            <tbody>
              {data?.map(b => (
                <tr key={b.id} className="border-b">
                  <td className="py-2">{b.id}</td>
                  <td>{b.title}</td>
                  <td>{b.author}</td>
                  <td>{b.stock}</td>
                  <td className="text-right space-x-2">
                    <button className="text-blue-600" onClick={() => { setEditId(b.id); setForm({ title:b.title, author:b.author, stock:b.stock }); }}>Edit</button>
                    <button className="text-red-600" onClick={() => remove(b.id)}>Delete</button>
                  </td>
                </tr>
              ))}
              {!data?.length && <tr><td colSpan={5} className="py-4 text-center text-gray-500">No data</td></tr>}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
