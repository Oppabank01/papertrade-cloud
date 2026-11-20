// Keeps the background Grok Bot tab alive for the Mac readers (read-only, sends no messages). A minimized Canary window
// gives the page a 0 px viewport and X's chat then hangs the tab (seen 20 Nov), so this holds one CDP session open with a
// 1280x900 viewport and focus emulation, and reloads the tab when a ping gets no answer for 60 s. agents.sh restarts it.
//   node grok_keeper.js
const CHAT = "chat/bots/5a365ff7-2a25-4cef-8a5f-42368835267a";
const log = (...a) => console.log(new Date().toISOString().slice(11, 19), ...a);
(async () => {
  const tab = (await (await fetch("http://127.0.0.1:9222/json")).json()).find(t => t.type === "page" && t.url.includes(CHAT));
  if (!tab) { log("no Grok Bot tab"); process.exit(1); }
  const ws = new WebSocket(tab.webSocketDebuggerUrl); let id = 0; const pend = {};
  const send = (method, params = {}) => new Promise(r => { const i = ++id; pend[i] = r; ws.send(JSON.stringify({ id: i, method, params })); });
  ws.onmessage = e => { const m = JSON.parse(e.data); if (m.id && pend[m.id]) { pend[m.id](m.result || m.error); delete pend[m.id]; } };
  ws.onclose = () => { log("tab closed or reconnect needed"); process.exit(0); };
  ws.onopen = async () => {
    send("Page.reload");                           // the page may already be hung: reload first (handled even then),
    await new Promise(r => setTimeout(r, 1500));   // then set the size while it loads, before X's chat code runs
    await send("Emulation.setDeviceMetricsOverride", { width: 1280, height: 900, deviceScaleFactor: 1, mobile: false });
    await send("Emulation.setFocusEmulationEnabled", { enabled: true });
    log("holding 1280x900");
    setInterval(async () => {
      const t = setTimeout(() => { log("no answer 60 s, reloading"); send("Page.reload"); }, 60000);
      await send("Runtime.evaluate", { expression: "1", returnByValue: true });
      clearTimeout(t);
    }, 120000);
  };
})();
