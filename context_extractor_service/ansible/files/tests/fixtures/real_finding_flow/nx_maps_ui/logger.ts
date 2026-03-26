export class Logger {
  constructor(private prefix: string, private showLevel = false) {}

  log(level: LogLevel, ...args: unknown[]) {
    let prefix = this.prefix;

    if (this.showLevel) {
      prefix = `- ${level} ${prefix}`;
    }

    if (level === LogLevel.ERROR) {
      console.error(prefix, ...args);
    } else {
      console.log(prefix, ...args);
    }
  }
}
