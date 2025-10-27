export default function Home() {
  return (
    <div className="space-y-2">
      <h1 className="text-2xl font-semibold">Library Frontend</h1>
      <p>Đi tới <a className="underline" href="/login">/login</a>, sau đó thử CRUD ở <a className="underline" href="/books">/books</a>, <a className="underline" href="/members">/members</a>, <a className="underline" href="/loans">/loans</a>.</p>
    </div>
  );
}
