export class GitOperations {
  async getBaseBranch() {
    return 'main';
  }

  async getParentBranch(remoteBranches) {
    try {
      if (remoteBranches.length > 0) {
        return remoteBranches[0];
      } else {
        return await this.getBaseBranch();
      }
    } catch (error) {
      if (process.env.DEBUG) {
        console.error('Error getting parent branch:', error);
      }
      return await this.getBaseBranch();
    }
  }
}
