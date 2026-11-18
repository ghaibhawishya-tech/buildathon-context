const historyKey = "ghost-shield-public-runs";
let publicRuns = [];
try {
  const stored = JSON.parse(localStorage.getItem(historyKey) || "[]");
  if (Array.isArray(stored)) publicRuns = stored;
} catch {
  // Continue with session-only results if storage is unavailable.
}

function rememberPublicRun(run) {
  publicRuns = [run, ...publicRuns].slice(0, 20);
  try { localStorage.setItem(historyKey, JSON.stringify(publicRuns)); }
  catch { /* The current session still has the evidence. */ }
}

function publicMetrics() {
  const recorded = publicRuns.length;
  const rehearsalDenials = publicRuns.flatMap(run => run.events)
    .filter(event => event.decision === "DENY" && event.origin === "manual rehearsal").length;
  return {
    by_mode: {
      fixture: {
        recorded, evaluated: recorded, completed: publicRuns.filter(run => run.task_completed).length,
        blocked: rehearsalDenials, model_denials: 0, rehearsal_denials: rehearsalDenials,
        average_duration_ms: recorded ? Math.round(publicRuns.reduce((sum, run) => sum + run.duration_ms, 0) / recorded * 100) / 100 : null,
      },
    },
    recent: publicRuns.slice(0, 12),
  };
}
