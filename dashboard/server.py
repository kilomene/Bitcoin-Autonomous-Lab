"""Live web dashboard for the lab (standard library only).

Serves one page that refreshes itself from /api/status every two
seconds: chain state, latest blocks, mempool, intelligence engine
sync state, autonomous mining statistics and decisions, and the
compute backend picture (CUDA verdict, C backend, benchmarks).
Binds to localhost by default.

Run: python3 -m dashboard.server [port]
"""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

PAGE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bitcoin Autonomous Lab - Live Dashboard</title>
<style>
body{background:#0b0e13;color:#e6edf3;font-family:ui-monospace,Menlo,monospace;margin:0;padding:20px}
h1{font-size:20px;margin:0 0 4px} .sub{color:#8b949e;margin-bottom:16px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:14px}
.card{background:#12161d;border:1px solid #26303d;border-radius:10px;padding:14px}
.card h2{font-size:13px;color:#f0b90b;margin:0 0 10px;text-transform:uppercase;letter-spacing:1px}
.kv{display:flex;justify-content:space-between;padding:3px 0;border-bottom:1px dashed #222b36}
.kv b{font-weight:600;text-align:right;word-break:break-all;margin-left:10px}
table{width:100%;border-collapse:collapse;font-size:12px}
td,th{padding:4px 2px;border-bottom:1px solid #1d242e;text-align:left}
.ok{color:#3fb950}.warn{color:#d29922}
</style></head><body>
<h1>Bitcoin Autonomous Lab</h1>
<div class="sub">Live dashboard, regtest node, refreshes every 2 seconds</div>
<div class="grid">
<div class="card"><h2>Chain</h2><div id="chain"></div></div>
<div class="card"><h2>Compute</h2><div id="compute"></div></div>
<div class="card"><h2>Autonomous Mining</h2><div id="mining"></div></div>
<div class="card"><h2>Mempool</h2><div id="mempool"></div></div>
<div class="card"><h2>Latest Blocks</h2><div id="blocks"></div></div>
<div class="card"><h2>Recent Decisions and Events</h2><div id="events"></div></div>
</div>
<script>
function kv(el, rows){ el.innerHTML = rows.map(r =>
  '<div class="kv"><span>'+r[0]+'</span><b>'+r[1]+'</b></div>').join(''); }
async function tick(){
  const d = await (await fetch('/api/status')).json();
  kv(document.getElementById('chain'), [
    ['network', d.chain.chain], ['height', d.chain.blocks],
    ['best block', d.chain.bestblockhash.slice(0,20)+'...'],
    ['difficulty', d.chain.difficulty],
    ['engine stored blocks', d.engine.stored_blocks],
    ['engine sync state', d.engine.sync.state]]);
  kv(document.getElementById('compute'), [
    ['backend', d.compute.backend],
    ['benchmark', Math.round(d.compute.benchmark_hs).toLocaleString()+' H/s'],
    ['CUDA', d.compute.cuda],
    ['C backend', d.compute.c_backend ? 'built (SHA-NI, midstate)' : 'not built']]);
  kv(document.getElementById('mining'), [
    ['cycles', d.mining.cycles], ['accepted', d.mining.accepted],
    ['total hashes', d.mining.total_hashes.toLocaleString()]]);
  kv(document.getElementById('mempool'), [
    ['transactions', d.mempool.size], ['bytes', d.mempool.bytes],
    ['total fees', d.mempool.total_fee_sats+' sats']]);
  document.getElementById('blocks').innerHTML =
    '<table><tr><th>height</th><th>hash</th><th>txs</th></tr>' +
    d.latest_blocks.map(b => '<tr><td>'+b.height+'</td><td>'+
      b.hash.slice(0,16)+'...</td><td>'+b.tx_count+'</td></tr>').join('') +
    '</table>';
  document.getElementById('events').innerHTML =
    '<table>' + d.events.map(e => '<tr><td>'+e.kind+'</td><td>'+
      String(e.detail).slice(0,80)+'</td></tr>').join('') + '</table>';
}
tick(); setInterval(tick, 2000);
</script></body></html>"""


def gather_status():
    from blockchain.store import BlockStore
    from blockchain.transactions import TxInspector
    from gpu.engine import ComputeEngine
    from node.rpc_client import BitcoinRPC
    rpc = BitcoinRPC()
    info = rpc.get_blockchain_info()
    store = BlockStore()
    engine = ComputeEngine()
    tip = info["blocks"]
    blocks = []
    for h in range(tip, max(tip - 8, -1), -1):
        b = rpc.get_block(rpc.get_block_hash(h), 1)
        blocks.append({"height": h, "hash": b["hash"],
                       "tx_count": len(b["tx"])})
    events = [{"kind": e["kind"], "detail": e["detail"]}
              for e in store.events(limit=8)]
    sync = store.get_sync()
    status = {
        "chain": {"chain": info["chain"], "blocks": info["blocks"],
                  "bestblockhash": info["bestblockhash"],
                  "difficulty": info["difficulty"]},
        "engine": {"stored_blocks": store.block_count(), "sync": sync},
        "mempool": TxInspector(rpc).mempool_snapshot(),
        "compute": {"backend": engine.backend,
                    "benchmark_hs": engine.benchmark(),
                    "cuda": engine.cuda_fallback_reason or "active",
                    "c_backend": engine.describe()["c_backend"]},
        "mining": store.mining_summary(),
        "latest_blocks": blocks,
        "events": events,
    }
    store.close()
    return status


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == "/api/status":
            body = json.dumps(gather_status()).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
        else:
            body = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main(port=8765):
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"dashboard on http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 8765)
