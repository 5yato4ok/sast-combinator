import fs from 'fs';

async function main() {
  const args = process.argv.slice(2);
  const engine = new TemplateEngine();

  try {
    let result = {};

    switch(args[0]) {
      case '--populate':
      case '-p':
        const templateName = args[1];
        const dataInput = args[2];
        let data;
        if (dataInput.endsWith('.json')) {
          data = JSON.parse(fs.readFileSync(dataInput, 'utf8'));
        } else {
          data = JSON.parse(dataInput);
        }
        result = await engine.getTemplateContent(templateName);
        break;
      case '--analyze':
      case '-a':
        const analysisInput = args[1];
        let analysisContext;
        if (analysisInput.endsWith('.json')) {
          analysisContext = JSON.parse(fs.readFileSync(analysisInput, 'utf8'));
        } else {
          analysisContext = JSON.parse(analysisInput);
        }
        result = engine.calculateScores(analysisContext);
        break;
    }

    return result;
  } catch (error) {
    console.error(error);
  }
}

main().catch(console.error);
