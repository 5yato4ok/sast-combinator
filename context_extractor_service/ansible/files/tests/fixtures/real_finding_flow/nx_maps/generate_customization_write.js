const fs = require('fs');

async function main() {
  const outputPath = `./output.json`;
  const config = { enabled: true };
  fs.writeFileSync(outputPath, JSON.stringify(config, null, 2), 'utf8');
}
