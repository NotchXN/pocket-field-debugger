// Usage: node tests/report-smoke.cjs demo-output/report.html
// Checks embedded JavaScript syntax, embedded demo data and handler wiring with a
// small DOM substitute. It is not a browser layout or rendering test.
const fs = require('fs');
const vm = require('vm');
const html = fs.readFileSync(process.argv[2], 'utf8');
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)];
if (scripts.length !== 1) throw new Error('Expected one embedded script');
const script = scripts[0][1];
new vm.Script(script);
const match = script.match(/^const session = (.*);$/m);
const session = JSON.parse(match[1]);
if (html.includes('/*SESSION_DATA*/null')) throw new Error('Template data missing');
if (session.summary.records !== 14 || session.summary.modbus_frames !== 8) throw new Error('Unexpected demo record counts');
if (session.summary.transactions_paired !== 2 || session.summary.unmatched_requests !== 1) throw new Error('Unexpected transaction counts');
if (session.transactions.length !== 3) throw new Error('Transactions were not embedded');

class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.style = {}; this.handlers = {}; this.dataset = {}; this.value = ''; this.textContent = ''; this.hidden = false; this.open = false; }
  appendChild(child) { this.children.push(child); return child; }
  append(...children) { this.children.push(...children); }
  setAttribute(key, value) { this[key] = value; }
  replaceChildren(...children) { this.children = children; }
  addEventListener(event, fn) { this.handlers[event] = fn; }
  click() { if (this.handlers.click) this.handlers.click(); }
}
const nodes = new Map([...html.matchAll(/\bid="([^"]+)"/g)].map(m => [m[1], new Element(m[1])]));
nodes.get('slider').value = '12';
nodes.get('low').value = '0';
nodes.get('high').value = '10';
nodes.get('unit').value = 'bar';
nodes.get('filter').value = 'all';
const context = {
  document: {
    getElementById(id) { if (!nodes.has(id)) throw new Error('Missing HTML element: ' + id); return nodes.get(id); },
    createElement: tag => new Element(tag),
    createElementNS: (_, tag) => new Element(tag),
  },
  URL: { createObjectURL() { return 'blob:smoke-check'; }, revokeObjectURL() {} },
  Blob,
  setTimeout: fn => fn(),
};
vm.runInNewContext(script, context);
if (nodes.get('rows').children.length !== 14) throw new Error('All-record table did not render');
if (nodes.get('transaction-rows').children.length !== 3) throw new Error('Transaction table did not render');
if (nodes.get('transactions').textContent !== '2') throw new Error('Transaction metric failed');
if (nodes.get('origin').textContent !== 'SIMULATED SESSION') throw new Error('Origin badge failed');
nodes.get('filter').value = 'issues';
nodes.get('filter').handlers.change();
if (nodes.get('rows').children.length !== 2) throw new Error('Issue filter failed');
nodes.get('filter').value = 'all';
nodes.get('search').value = 'frame-004';
nodes.get('search').handlers.input();
if (nodes.get('rows').children.length !== 1) throw new Error('Search failed');
nodes.get('rows').children[0].children[5].children[0].click();
if (!nodes.get('detail').textContent.includes('"exception_code": 2')) throw new Error('Inspect action failed');
nodes.get('slider').value = '3.5';
nodes.get('slider').handlers.input();
if (nodes.get('range-status').textContent !== 'Below the 4 mA range') throw new Error('Calculator range status failed');
if (nodes.get('namur-status').textContent !== 'NAMUR NE 43: failure (low)') throw new Error('Calculator NAMUR status failed');
nodes.get('slider').value = '20.8';
nodes.get('slider').handlers.input();
if (nodes.get('namur-status').textContent !== 'NAMUR NE 43: saturated (high)') throw new Error('Calculator NAMUR saturation failed');
nodes.get('download').click();
console.log(JSON.stringify({script_syntax: 'passed', embedded_records: 14, embedded_transactions: 3, dom_smoke: 'passed', browser_visual_test: 'not performed'}));
