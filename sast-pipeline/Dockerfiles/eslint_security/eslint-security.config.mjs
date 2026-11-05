// config/eslint-security.config.mjs
import tsparser from "@typescript-eslint/parser";
import security from "eslint-plugin-security";
import nous from "eslint-plugin-no-unsanitized";


export default [
  {
    files: ["**/*.{js,jsx,ts,tsx}"],
    languageOptions: {
      parser: tsparser,
      ecmaVersion: "latest",
      sourceType: "module"
    },
    plugins: {
      security,
      "no-unsanitized": nous
    },
    rules: {

      "security/detect-unsafe-regex": "warn",
      "security/detect-buffer-noassert": "warn",
      "security/detect-child-process": "warn",
      "security/detect-disable-mustache-escape": "warn",
      "security/detect-eval-with-expression": "warn",
      "security/detect-new-buffer": "warn",
      "security/detect-no-csrf-before-method-override": "warn",
      "security/detect-non-literal-fs-filename": "warn",
      "security/detect-non-literal-regexp": "warn",
      "security/detect-non-literal-require": "warn",
      "security/detect-object-injection": "warn",
      "security/detect-possible-timing-attacks": "warn",
      "security/detect-pseudoRandomBytes": "warn",


      "no-unsanitized/method": "warn",
      "no-unsanitized/property": "warn",


      "no-eval": "warn",
      "no-implied-eval": "warn",
      "no-new-func": "warn",
      "no-script-url": "warn"
    }
  }
];
