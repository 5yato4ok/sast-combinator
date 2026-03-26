export class GitOperations {
  async runCommand(command) {
    return command;
  }

  async getBaseBranch() {
    return 'main';
  }

  async detectBranchPoint() {
    try {
      const currentBranch = await this.runCommand('git branch --show-current');
      if (process.env.DEBUG) {
        console.error(`Detecting branch point for: ${currentBranch}`);
      }

      const commits = ['abc1234'];
      for (const commit of commits) {
        try {
          const branchesOutput = await this.runCommand(`git branch -a --contains ${commit}`);
          const branches = branchesOutput.split('\n').filter(Boolean);
          if (branches.length > 0) {
            if (process.env.DEBUG) {
              console.error(`Found branch point using primary method: ${commit}`);
            }
            return commit;
          }
        } catch (e) {
        }
      }

      throw new Error('boom');
    } catch (error) {
      if (process.env.DEBUG) {
        console.error('Error detecting branch point:', error);
      }
      return null;
    }
  }

  async runCommandWithRetry(command, maxRetries, retryableErrors, baseDelay, timeout) {
    for (let attempt = 1; attempt <= maxRetries; attempt++) {
      try {
        const result = execSync(command, {
          encoding: 'utf8',
          maxBuffer: 10 * 1024 * 1024,
          cwd: process.cwd(),
          timeout: timeout
        });

        return result.trim();
      } catch (error) {
        const errorMessage = error.message || '';
        const isRetryable = retryableErrors.some(pattern => pattern.test(errorMessage));

        if (attempt === maxRetries || !isRetryable) {
          throw new Error(`Command failed: ${errorMessage}`);
        }

        const delay = baseDelay * Math.pow(2, attempt - 1);
        if (process.env.DEBUG) {
          console.error(`Attempt ${attempt} failed for command: ${command.substring(0, 50)}...`);
          console.error(`Retrying in ${delay}ms...`);
        }

        await new Promise(resolve => setTimeout(resolve, delay));
      }
    }
  }
}
