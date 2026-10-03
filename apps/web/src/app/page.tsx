import { Chat } from "@/components/Chat";

export default function Home() {
  return (
    <main className="page">
      <header className="masthead">
        <h1>CBA Analyzer</h1>
        <p className="muted">
          Questions about the 2023 NBA Collective Bargaining Agreement, answered from its text and
          a snapshot of league data, or declined with a reason.
        </p>
        <p className="masthead-links">
          <a href="/cap">Team cap sheets</a>
        </p>
      </header>
      <Chat />
      <footer className="page-footer muted">
        An independent project, not affiliated with the NBA or the NBPA. Not legal advice. League
        data is a scraped snapshot; every figure says when it was observed.
      </footer>
    </main>
  );
}
