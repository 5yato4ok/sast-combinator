import fs from 'fs';

async function main() {
  const args = process.argv.slice(2);
  const extractor = new ContextExtractor();

  try {
    let result = {};

    switch(args[0]) {
      case '--extract':
      case '-e':
        const gitDataInput = args[1];
        let gitData;
        if (gitDataInput && gitDataInput.endsWith('.json')) {
          gitData = JSON.parse(fs.readFileSync(gitDataInput, 'utf8'));
        }
        result = await extractor.extractContext(gitData);
        break;
      case '--semantic':
      case '-s':
        const commitsInput = args[1];
        let commits;
        if (commitsInput && commitsInput.endsWith('.json')) {
          commits = JSON.parse(fs.readFileSync(commitsInput, 'utf8'));
        } else if (commitsInput) {
          commits = JSON.parse(commitsInput);
        }
        result = extractor.analyzeSemantics(commits);
        break;
      case '--components':
      case '-c':
        const filesInput = args[1];
        let files;
        if (filesInput && filesInput.endsWith('.json')) {
          files = JSON.parse(fs.readFileSync(filesInput, 'utf8'));
        } else if (filesInput) {
          files = JSON.parse(filesInput);
        }
        result = extractor.detectComponents(files);
        break;
      case '--metadata':
      case '-m':
        const metaDataInput = args[1];
        let metaData;
        if (metaDataInput && metaDataInput.endsWith('.json')) {
          metaData = JSON.parse(fs.readFileSync(metaDataInput, 'utf8'));
        } else if (metaDataInput) {
          metaData = JSON.parse(metaDataInput);
        }
        result = extractor.extractMetadata(metaData);
        break;
    }

    return result;
  } catch (error) {
    console.error(error);
  }
}

main().catch(console.error);
