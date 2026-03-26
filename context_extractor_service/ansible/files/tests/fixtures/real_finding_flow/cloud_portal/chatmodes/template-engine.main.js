class TemplateEngine {
  async getTemplateContent(templateName) {
    const templatePath = path.join(process.cwd(), '.gitlab/merge_request_templates', templateName);
    try {
      return fs.readFileSync(templatePath, 'utf8');
    } catch (error) {
      throw new Error(`Failed to read template ${templateName}: ${error.message}`);
    }
  }

  populateTemplate(template, data) {
    let content = template;

    const replacements = {
      '{{issue}}': data.issue || 'N/A',
      '{{branch}}': data.branch || 'current-branch',
      '{{summary}}': data.summary || 'Summary pending',
      '{{description}}': data.description || 'Description pending',
      '{{components}}': data.components?.join(', ') || 'Various',
      '{{tests}}': data.tests || 'Tests pending',
      '{{breaking}}': data.breaking || 'None identified',
    };

    for (const [placeholder, value] of Object.entries(replacements)) {
      content = content.replace(new RegExp(placeholder, 'g'), value);
    }

    return content;
  }
}

async function main() {
  const args = process.argv.slice(2);
  const engine = new TemplateEngine();

  try {
    let result = {};

    switch (args[0]) {
      case '--score':
      case '-s':
        const contextInput = args[1];
        let context;

        if (contextInput.endsWith('.json')) {
          context = JSON.parse(fs.readFileSync(contextInput, 'utf8'));
        } else {
          context = JSON.parse(contextInput);
        }

        result = engine.calculateScores(context);
        break;

      case '--select':
      case '-e':
        const scoresInput = args[1];
        let scores;

        if (scoresInput.endsWith('.json')) {
          scores = JSON.parse(fs.readFileSync(scoresInput, 'utf8'));
        } else {
          scores = JSON.parse(scoresInput);
        }

        result = engine.selectTemplate(scores);
        break;

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

        const template = await engine.getTemplateContent(templateName);
        result = {
          content: engine.populateTemplate(template, data),
          template: templateName,
        };
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

        try {
          const gitContextPath = '/tmp/git-context.json';
          if (fs.existsSync(gitContextPath)) {
            const gitContext = JSON.parse(fs.readFileSync(gitContextPath, 'utf8'));
            if (Array.isArray(gitContext) && gitContext.length >= 3) {
              if (!analysisContext.files || analysisContext.files.length === 0) {
                if (gitContext[1] && typeof gitContext[1] === 'string') {
                  const lines = gitContext[1].split('\n').filter(l => l.trim());
                  analysisContext.files = lines
                    .map(line => {
                      const parts = line.split('\t');
                      return parts.length > 1 ? parts[1] : line;
                    })
                    .filter(f => f);
                }
              }
            }
          }
        } catch (err) {
        }

        const analysisScores = engine.calculateScores(analysisContext);
        result = engine.selectTemplate(analysisScores);
        result.scores = analysisScores;
        break;
    }

    return result;
  } catch (error) {
    throw error;
  }
}
