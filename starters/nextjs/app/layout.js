import './globals.css';

export const metadata = {
  title: 'MossCMS published entries',
  description: 'Published entries read from MossCMS with the shared delivery client.',
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        <header className="banner">
          <p className="brand">MossCMS</p>
        </header>
        {children}
      </body>
    </html>
  );
}
