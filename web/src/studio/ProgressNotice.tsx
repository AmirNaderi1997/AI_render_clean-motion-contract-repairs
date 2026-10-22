import React from 'react';

/** A wall clock is not a progress estimate. Never advance the engine's percentage. */
export function useProgressAge(running: boolean, progress: number | undefined, stage: string) {
  const [reportedAt, setReportedAt] = React.useState(() => Date.now());
  const [now, setNow] = React.useState(() => Date.now());
  React.useEffect(() => { setReportedAt(Date.now()); setNow(Date.now()); }, [progress, stage, running]);
  React.useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [running]);
  return running ? Math.max(0, Math.floor((now - reportedAt) / 1000)) : 0;
}

export function ProgressNotice({seconds}: {seconds: number}) {
  return seconds >= 30 ? <p className="ws-hint" role="status" dir="auto">در انتظار گزارش تازه از موتور · {seconds} ثانیه از آخرین تغییر وضعیت گذشته است. زمان پایان هنوز مشخص نیست.</p> : null;
}
