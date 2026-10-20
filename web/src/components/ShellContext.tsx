import React from "react";

type ShellValue = { openNav: () => void; setTitle: (title: string) => void };
export const ShellContext = React.createContext<ShellValue>({ openNav: () => undefined, setTitle: () => undefined });

/** Let a page set the mobile top-bar title while it is mounted. */
export function useTopbarTitle(title: string | undefined) {
  const { setTitle } = React.useContext(ShellContext);
  React.useEffect(() => { setTitle(title || ""); return () => setTitle(""); }, [title, setTitle]);
}
