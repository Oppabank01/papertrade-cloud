// One CDP session on the background Grok Bot tab (Mac only, read-only): reload, emulate focus, then wheel down with a tiny
// screenshot per step (a hidden tab draws no frames, so X's scroll loader never fires without it) until the newest message
// is loaded. Prints {key: text} of every message seen. Used by grokscout.records().
//   node grok_sweep.js <tab ws url> <PANE js> <reload 0|1> [text to wheel up to first, e.g. "LEDGER S9 00:50", for filling a hole]
const ws = new WebSocket(process.argv[2]); let id = 0; const pend = {};
const send = (method, params = {}) => new Promise(r => { const i = ++id; pend[i] = r; ws.send(JSON.stringify({ id: i, method, params })); });
ws.onmessage = e => { const m = JSON.parse(e.data); if (m.id && pend[m.id]) { pend[m.id](m.result || m.error); delete pend[m.id]; } };
const PANE = process.argv[3], sleep = ms => new Promise(r => setTimeout(r, ms));
const ev = async js => (await send("Runtime.evaluate", { expression: "(()=>{" + PANE + js + "})()", returnByValue: true }))?.result?.value;
const ITEMS = "return JSON.stringify(s?[...s.querySelectorAll('[data-dm-item-key]')].map(e=>[e.dataset.dmItemKey,e.textContent]):[])";
const frame = () => send("Page.captureScreenshot", { format: "jpeg", quality: 10, clip: { x: 0, y: 0, width: 40, height: 40, scale: 0.2 } });
const want = process.argv[5], got = {};   // fill mode: wheel up until a message containing `want` loads, allow 15 min
setTimeout(() => { process.stdout.write(JSON.stringify(got)); process.exit(2); }, want ? 900000 : 150000);   // keep what was read
ws.onopen = async () => {
  await send("Page.enable");
  await send("Emulation.setFocusEmulationEnabled", { enabled: true });
  // a minimized or tiny window (innerWidth 8 seen 20 Nov) collapses X's layout: give the page its own 1280x900 viewport
  await send("Emulation.setDeviceMetricsOverride", { width: 1280, height: 900, deviceScaleFactor: 1, mobile: false });
  if (process.argv[4] === "1") { await send("Page.reload"); await sleep(4000); }
  let xy = null;
  for (let i = 0; i < 20 && !xy; i++) {
    await frame();
    const v = await ev("if(!s||!s.querySelector('[data-dm-item-key]'))return null;const r=s.getBoundingClientRect();return JSON.stringify([r.x+r.width/2,r.y+r.height/2])");
    xy = v && JSON.parse(v);
    if (!xy) await sleep(2000);
  }
  if (!xy) process.exit(3);
  for (let i = 0; want && i < 400 && !Object.values(got).some(v => v.includes(want)); i++) {
    for (const [k, v] of JSON.parse(await ev(ITEMS) || "[]")) got[k] = v;
    await send("Input.dispatchMouseEvent", { type: "mouseWheel", x: xy[0], y: xy[1], deltaX: 0, deltaY: -1200 });
    await frame();
    await sleep(1000);
  }
  let flat = 0;
  for (let i = 0; i < (want ? 1500 : 120) && flat < 10; i++) {
    const n = Object.keys(got).length;
    for (const [k, v] of JSON.parse(await ev(ITEMS) || "[]")) got[k] = v;
    const bottom = await ev("return s.scrollTop+s.clientHeight>=s.scrollHeight-5");
    flat = bottom && Object.keys(got).length === n ? flat + 1 : 0;
    await send("Input.dispatchMouseEvent", { type: "mouseWheel", x: xy[0], y: xy[1], deltaX: 0, deltaY: 600 });
    await frame();
    await sleep(1000);
  }
  process.stdout.write(JSON.stringify(got));
  process.exit(0);
};
