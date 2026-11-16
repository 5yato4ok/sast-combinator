import { readdirSync, statSync } from "node:fs";
import path from "node:path";

const SKIPPED_DIRECTORIES = new Set(["node_modules", ".git"]);
const GLOB_SYNTAX = /[\\*?[\]{}()!+@#]/g;

/**
 * Ignore patterns, relative to `root`, for every symlink under it that resolves to nothing
 * (dangling, or a loop such as `a.js -> a.js`). Each pattern matches only its own path.
 */
export function unresolvableLinkPatterns(root) {
  const patterns = [];
  const walk = (directory) => {
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      const entryPath = path.join(directory, entry.name);
      if (entry.isDirectory() && !SKIPPED_DIRECTORIES.has(entry.name)) {
        walk(entryPath);
      } else if (entry.isSymbolicLink()) {
        try {
          statSync(entryPath);
        } catch {
          patterns.push(path.relative(root, entryPath).replace(GLOB_SYNTAX, "\\$&"));
        }
      }
    }
  };
  walk(root);
  return patterns;
}
