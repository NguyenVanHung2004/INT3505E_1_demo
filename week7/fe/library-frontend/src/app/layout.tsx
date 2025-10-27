import "./globals.css";
import Link from "next/link";

export const metadata = { title: "Library FE" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="vi">
      <body className="min-h-screen bg-gray-50 text-gray-900">
        <header className="border-b bg-white">
          <nav className="container mx-auto px-4 h-14 flex items-center gap-4">
            <Link href="/" className="font-semibold">Library</Link>
            <Link href="/books" className="hover:underline">Books</Link>
            <Link href="/members" className="hover:underline">Members</Link>
            <Link href="/loans" className="hover:underline">Loans</Link>
            <div className="ml-auto flex items-center gap-3">
              <Link href="/login" className="text-sm px-3 py-1.5 rounded border">Login</Link>
              <form action="/api/logout" method="post">
                <button className="text-sm px-3 py-1.5 rounded border">Logout</button>
              </form>
            </div>
          </nav>
        </header>
        <main className="container mx-auto px-4 py-6">{children}</main>
      </body>
    </html>
  );
}
