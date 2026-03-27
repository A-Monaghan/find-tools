import { readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

const DIST_ASSETS = join(process.cwd(), 'dist', 'assets');
const INDEX_JS_BUDGET_BYTES = 360 * 1024;
const GRAPH_CHUNK_BUDGET_BYTES = 220 * 1024;

function fail(message) {
  console.error(`Bundle budget check failed: ${message}`);
  process.exit(1);
}

const files = readdirSync(DIST_ASSETS);
const indexJs = files.find((f) => /^index-.*\.js$/.test(f));
if (!indexJs) fail('Could not find index-*.js in dist/assets.');

const indexSize = statSync(join(DIST_ASSETS, indexJs)).size;
if (indexSize > INDEX_JS_BUDGET_BYTES) {
  fail(`main bundle ${indexJs} is ${(indexSize / 1024).toFixed(1)}KB (budget: ${INDEX_JS_BUDGET_BYTES / 1024}KB).`);
}

const graphJs = files.find((f) => /^react-force-graph-2d-.*\.js$/.test(f));
if (graphJs) {
  const graphSize = statSync(join(DIST_ASSETS, graphJs)).size;
  if (graphSize > GRAPH_CHUNK_BUDGET_BYTES) {
    fail(`graph chunk ${graphJs} is ${(graphSize / 1024).toFixed(1)}KB (budget: ${GRAPH_CHUNK_BUDGET_BYTES / 1024}KB).`);
  }
}

console.log(
  `Bundle budgets OK: ${indexJs} ${(indexSize / 1024).toFixed(1)}KB` +
    (graphJs ? `, ${graphJs} ${(statSync(join(DIST_ASSETS, graphJs)).size / 1024).toFixed(1)}KB` : '')
);

