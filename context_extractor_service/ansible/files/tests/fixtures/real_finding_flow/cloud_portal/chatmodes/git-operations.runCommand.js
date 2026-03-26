class GitOperations {
  async runCommand(command, options = {}) {
    const maxRetries = options.retries || 3;
    const baseDelay = options.delay || 1000;
    const timeout = options.timeout || 30000;

    const retryableErrors = [
      /index\.lock/,
      /unable to access/,
      /connection timed out/i,
      /could not read from remote/i,
      /RPC failed/,
      /early EOF/,
    ];

    for (let attempt = 1; attempt <= maxRetries; attempt++) {
      try {
        const result = execSync(command, {
          encoding: 'utf8',
          maxBuffer: 10 * 1024 * 1024,
          cwd: process.cwd(),
          timeout: timeout,
        });

        return result.trim();
      } catch (error) {
        const errorMessage = error.message || '';
        const isRetryable = retryableErrors.some(pattern => pattern.test(errorMessage));

        if (errorMessage.includes('index.lock')) {
          try {
            execSync('rm -f .git/index.lock', { encoding: 'utf8' });
          } catch {}
        }

        if (attempt === maxRetries || !isRetryable) {
          throw new Error(`Command failed: ${errorMessage}`);
        }

        const delay = baseDelay * Math.pow(2, attempt - 1);
        await new Promise(resolve => setTimeout(resolve, delay));
      }
    }
  }
}
