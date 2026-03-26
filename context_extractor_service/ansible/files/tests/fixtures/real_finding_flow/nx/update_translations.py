from pathlib import Path


def calculateEntries(filename, translationDir, language):
    return [filename, translationDir, language]


def update_translations(projectDir, project, translationDir, language, lupdate):
    sourcesDir = projectDir / project.sources
    filename = project.name

    entries = calculateEntries(filename, translationDir, language)

    command = [lupdate, '-no-obsolete', '-no-ui-lines']
    command.append('-locations')
    command.append(project.locations)
    command.append('-extensions')
    command.append(project.extensions)

    return sourcesDir, entries, command
