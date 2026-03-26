function runCommand(command) {
  return execSync(command, {
    encoding: 'utf8',
    maxBuffer: 10 * 1024 * 1024,
    cwd: process.cwd(),
    timeout: timeout,
  });
}

function first() {
  return 1;
}

function second() {
  return 2;
}

function third() {
  return 3;
}

const result = execSync(command, {
  encoding: 'utf8',
  maxBuffer: 10 * 1024 * 1024,
  cwd: process.cwd(),
  timeout: timeout,
});

runCommand(command);






runCommand(command);








runCommand(command);
