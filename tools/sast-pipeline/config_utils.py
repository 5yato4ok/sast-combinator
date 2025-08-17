import yaml

class AnalyzersConfigHelper:

    analyzers: list[dict[str, object]] = None
    languages = None
    def __init__(self, config_path):
        self.config_path = config_path
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        self.analyzers = config.get("analyzers", [])

    def get_analyzers(self):
        return self.analyzers

    def get_supported_languages(self):
        if not self.analyzers:
            raise Exception("Analyzers list is empty")

        if self.languages:
            return  self.languages

        self.languages = list({analyzer.get("language")
                               for analyzer in self.analyzers
                               if "language" in analyzer})

        return self.languages


    def prepare_pipeline_analyzer_config(self):
        pass