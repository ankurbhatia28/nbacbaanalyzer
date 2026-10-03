import type { Metadata } from "next";

import { CapSheetView } from "@/components/CapSheetView";
import { TeamPicker } from "@/components/TeamPicker";

export async function generateMetadata(props: PageProps<"/cap/[team]">): Promise<Metadata> {
  const { team } = await props.params;
  return { title: `${team.toUpperCase()} cap sheet · CBA Analyzer` };
}

export default async function TeamSheet(props: PageProps<"/cap/[team]">) {
  const { team } = await props.params;
  const key = team.toUpperCase();
  return (
    <main className="page page-wide">
      <header className="masthead">
        <h1>
          <a href="/" className="home-link">
            CBA Analyzer
          </a>
        </h1>
      </header>
      <TeamPicker current={key} compact />
      <CapSheetView team={key} />
    </main>
  );
}
