import React from "react";

export type TopbarAction = { active: boolean; onClick: () => void };
type ShellValue = { openNav: () => void; setTitle: (title: string) => void; setAction: (action: TopbarAction | null) => void };
export const ShellContext = React.createContext<ShellValue>({ openNav: () => undefined, setTitle: () => undefined, setAction: () => undefined });

export function useTopbarAction(action: TopbarAction | null) {
  const { setAction } = React.useContext(ShellContext);
  React.useEffect(() => { setAction(action); return () => setAction(null); }, [action, setAction]);
}

/** Let a page set the mobile top-bar title while it is mounted. */
export function useTopbarTitle(title: string | undefined) {
  const { setTitle } = React.useContext(ShellContext);
  React.useEffect(() => { setTitle(title || ""); return () => setTitle(""); }, [title, setTitle]);
}
