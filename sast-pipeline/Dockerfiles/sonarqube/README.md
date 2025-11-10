# SonarQube Scanner Analyzer

Runs **sonar-scanner** to submit analysis to a SonarQube/SonarCloud server, then fetches issues JSON.

## Quick start

```bash
docker build -t sonarqube-analyzer .
docker run --rm -v "$PWD":/workspace -v "$PWD/out":/shared/output \  -e SONAR_HOST_URL="https://sonar.your.org" \  -e SONAR_TOKEN="***" \  -e SONAR_PROJECT_KEY="your_project_key" \  sonarqube-analyzer /analyze.sh /workspace /shared/output
```

## Required env
- `SONAR_HOST_URL`, `SONAR_TOKEN`, `SONAR_PROJECT_KEY`
- Optional: `SONAR_ORGANIZATION`, `SONAR_SCANNER_OPTS`

## Output
- `sonarqube-scan.log`
- `sonarqube.json` (issues via Web API)
