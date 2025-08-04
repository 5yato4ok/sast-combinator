# DevSkim

Image runs [DevSkim](https://github.com/microsoft/DevSkim), a static analysis tool by Microsoft for detecting security issues in source code.

## Features

- No build system required (can work without `compile_commands.json`)
- Outputs SARIF

## Types of Checks

DevSkim is a lightweight SAST tool from Microsoft that scans source code for security-related patterns and bad practices.
It uses regex-based rules organized by language and vulnerability class. Below are the main types of checks it performs:

| Category                     | Description                                                             |
| -----------------------------| ----------------------------------------------------------------------- |
|  **Credential leaks**        | Hardcoded secrets, API keys, tokens, passwords                          |
|  **Weak crypto**             | Use of insecure algorithms (e.g., MD5, SHA1, outdated TLS versions)     |
|  **Insecure transmission**   | Unencrypted HTTP, FTP, etc.                                             |
|  **Command injection**       | Dangerous use of `exec`, `system`, or shell input                       |
|  **Insecure loops / logic**  | Use of insecure or risky control structures                             |
|  **Insecure dependencies**   | Outdated or known-vulnerable libraries (limited)                        |
|  **Input validation**        | Missing or weak validation on user input                                |
|  **Improper access control** | Insecure ACLs, bad role checks                                          |
|  **File access issues**      | Insecure file handling (e.g., temp files, symlinks, unsafe permissions) |
|  **Misconfiguration**        | Dangerous settings in source (e.g., debug enabled in production code)   |
|  **Hardcoded strings**       | Hardcoded URIs, secrets, debug messages, emails, etc.                   |

## Supported Languages

 - C
 - Objective C
 - C++
 - C#
 - Cobol
 - Go
 - Java
 - Javascript/Typescript
 - PHP
 - Powershell
 - Python
 - Ruby
 - Rust
 - SQL
 - Swift
 - Visual Basic

## Build image

```bash
cd docker
docker build -t devskim-analyzer .
```

## Run

```bash
docker run --rm -v "$PWD:/src" devskim-analyzer
```