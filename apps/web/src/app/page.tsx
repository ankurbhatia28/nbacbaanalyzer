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
          <a href="/cap">Team cap sheets</a> · <a href="/trade">Trade builder</a>
        </p>
      </header>
      <Chat />
      <footer className="page-footer muted">
        An independent project, not affiliated with the NBA or the NBPA. Not legal advice. League
        data is a scraped snapshot; every figure says when it was observed. Questions are logged to
        improve the app, and when the main model is unavailable a free third-party model may answer,
        whose provider may keep what it is sent: don&apos;t include anything private.
      </footer>
    </main>
  );
}
