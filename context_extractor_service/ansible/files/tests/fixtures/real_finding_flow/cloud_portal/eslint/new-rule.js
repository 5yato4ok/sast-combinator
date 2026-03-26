const fs = require('fs');

const newRuleName = process.argv[2] && process.argv[2].trim();
const ruleFile = 'export default "rule-name";';

fs.writeFileSync(`./src/rules/${newRuleName}.ts`, ruleFile.replace(/rule-name/g, newRuleName));
