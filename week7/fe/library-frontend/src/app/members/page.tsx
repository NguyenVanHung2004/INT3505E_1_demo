"use client";
import useSWR from "swr";
import { api } from "@/lib/api";
import { useState } from "react";
type Member = { id:number; name:string; email:string };
const fetcher = (u:string)=>api.get(u).then(r=>r.data);

export default function MembersPage(){
  const { data, mutate } = useSWR<Member[]>("/api/v1/members", fetcher);
  const [form, setForm] = useState({ name:"", email:"" });
  const [editId, setEditId] = useState<number|null>(null);

  async function create(){ await api.post("/api/v1/members", form); setForm({name:"",email:""}); mutate(); }
  async function update(){ if(!editId) return; await api.put(`/api/v1/members/${editId}`, form); setEditId(null); setForm({name:"",email:""}); mutate(); }
  async function remove(id:number){ await api.delete(`/api/v1/members/${id}`); mutate(); }

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Members</h1>
      <div className="bg-white border rounded-2xl p-4 shadow space-y-3">
        <div className="grid md:grid-cols-2 gap-3">
          <input className="border rounded px-3 py-2" placeholder="Name" value={form.name} onChange={e=>setForm(f=>({...f,name:e.target.value}))}/>
          <input className="border rounded px-3 py-2" placeholder="Email" value={form.email} onChange={e=>setForm(f=>({...f,email:e.target.value}))}/>
        </div>
        <div className="flex gap-3">
          {!editId ? <button onClick={create} className="px-4 py-2 bg-black text-white rounded">Create</button>
                   : <button onClick={update} className="px-4 py-2 bg-blue-600 text-white rounded">Update</button>}
          {editId && <button onClick={()=>{setEditId(null); setForm({name:"",email:""});}} className="px-4 py-2 border rounded">Cancel</button>}
        </div>
      </div>
      <div className="bg-white border rounded-2xl p-4 shadow">
        <table className="w-full">
          <thead><tr className="text-left border-b"><th className="py-2">ID</th><th>Name</th><th>Email</th><th></th></tr></thead>
          <tbody>
            {data?.map(m=>(
              <tr key={m.id} className="border-b">
                <td className="py-2">{m.id}</td><td>{m.name}</td><td>{m.email}</td>
                <td className="text-right space-x-2">
                  <button className="text-blue-600" onClick={()=>{setEditId(m.id); setForm({name:m.name,email:m.email});}}>Edit</button>
                  <button className="text-red-600" onClick={()=>remove(m.id)}>Delete</button>
                </td>
              </tr>
            )) || <tr><td colSpan={4} className="py-4 text-center text-gray-500">No data</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
