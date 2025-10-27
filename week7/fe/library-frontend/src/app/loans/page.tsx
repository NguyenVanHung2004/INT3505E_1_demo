"use client";
import useSWR from "swr";
import { api } from "@/lib/api";
import { useState } from "react";
type Loan = { id:number; book_id:number; member_id:number; loan_date:string; return_date:string|null };
const fetcher = (u:string)=>api.get(u).then(r=>r.data);

export default function LoansPage(){
  const { data, mutate } = useSWR<Loan[]>("/api/v1/loans", fetcher);
  const [form, setForm] = useState({ book_id: 0, member_id: 0, return_date: "" });
  const [editId, setEditId] = useState<number|null>(null);

  async function create(){ await api.post("/api/v1/loans", { book_id:Number(form.book_id), member_id:Number(form.member_id) }); setForm({book_id:0,member_id:0,return_date:""}); mutate(); }
  async function update(){ if(!editId) return; const body:any={}; if(form.return_date) body.return_date=form.return_date; await api.put(`/api/v1/loans/${editId}`, body); setEditId(null); setForm({book_id:0,member_id:0,return_date:""}); mutate(); }
  async function remove(id:number){ await api.delete(`/api/v1/loans/${id}`); mutate(); }

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Loans</h1>
      <div className="bg-white border rounded-2xl p-4 shadow space-y-3">
        <div className="grid md:grid-cols-3 gap-3">
          <input className="border rounded px-3 py-2" placeholder="Book ID" type="number" value={form.book_id} onChange={e=>setForm(f=>({...f,book_id:Number(e.target.value)}))}/>
          <input className="border rounded px-3 py-2" placeholder="Member ID" type="number" value={form.member_id} onChange={e=>setForm(f=>({...f,member_id:Number(e.target.value)}))}/>
          <input className="border rounded px-3 py-2" placeholder="Return ISO (optional)" value={form.return_date} onChange={e=>setForm(f=>({...f,return_date:e.target.value}))}/>
        </div>
        <div className="flex gap-3">
          {!editId ? <button onClick={create} className="px-4 py-2 bg-black text-white rounded">Create Loan</button>
                   : <button onClick={update} className="px-4 py-2 bg-blue-600 text-white rounded">Update Loan</button>}
          {editId && <button onClick={()=>{setEditId(null); setForm({book_id:0,member_id:0,return_date:""});}} className="px-4 py-2 border rounded">Cancel</button>}
        </div>
      </div>
      <div className="bg-white border rounded-2xl p-4 shadow">
        <table className="w-full">
          <thead><tr className="text-left border-b"><th className="py-2">ID</th><th>Book</th><th>Member</th><th>Loan</th><th>Return</th><th></th></tr></thead>
        <tbody>
          {data?.map(l=>(
            <tr key={l.id} className="border-b">
              <td className="py-2">{l.id}</td><td>{l.book_id}</td><td>{l.member_id}</td>
              <td>{new Date(l.loan_date).toLocaleString()}</td><td>{l.return_date ? new Date(l.return_date).toLocaleString() : "-"}</td>
              <td className="text-right space-x-2">
                <button className="text-blue-600" onClick={()=>{setEditId(l.id);}}>Edit</button>
                <button className="text-red-600" onClick={()=>remove(l.id)}>Delete</button>
              </td>
            </tr>
          )) || <tr><td colSpan={6} className="py-4 text-center text-gray-500">No data</td></tr>}
        </tbody>
        </table>
      </div>
    </div>
  );
}
