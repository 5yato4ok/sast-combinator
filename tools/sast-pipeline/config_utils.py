import yaml
import os
import copy
from docker_utils import get_pipeline_id

class AnalyzersConfigHelper:
    ANALYZER_ORDER = {
        "fast": 0,
        "medium": 1,
        "slow": 2,
    }
    analyzers: list[dict[str, object]] = None
    languages = None

    def __init__(self, config_path, ):
        self.config_path = config_path
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        self.analyzers = AnalyzersConfigHelper.expand_analyzers(
            config.get("analyzers", []),
            allowed_langs=self.languages or None,
            keep_parent=False
        )

    @staticmethod
    def get_analyzer_result_file_name(analyzer):
        name = analyzer.get("name")
        output_type = analyzer.get("output_type", "sarif")
        ext = "sarif" if output_type.lower() == "sarif" else "json"
        return analyzer.get("result_file", f"{name}_result.{ext}")

    def get_analyzers_time_class(self):
        return self.ANALYZER_ORDER.keys()

    def get_analyzers(self):
        return self.analyzers

    def get_supported_analyzers(self):
        if not self.analyzers:
            raise Exception("Analyzers list is empty")

        supported_analyzers = list({analyzer.get("name")
                               for analyzer in self.analyzers})
        return supported_analyzers

    def get_supported_languages(self):
        if not self.analyzers:
            raise Exception("Analyzers list is empty")

        if self.languages:
            return  self.languages

        self.languages = list({analyzer.get("language")
                               for analyzer in self.analyzers
                               if "language" in analyzer})

        return self.languages

    @staticmethod
    def get_level(time_class: str) -> int:
        return AnalyzersConfigHelper.ANALYZER_ORDER.get(time_class, 100)

    @staticmethod
    def expand_analyzers(analyzers, allowed_langs=None, keep_parent=False):
        """
        Expand analyzers that have language_specific_containers=True:
          - For each {<lang>: { ... }} entry in `configuration` produce a new analyzer.
          - Child config overrides parent fields (image, type, dockerfile_path, etc).
          - Sets `language` to [<lang>] and adds `effective_name` = "<name>[<lang>]".
        Args:
          analyzers: list[dict] — original analyzers.
          allowed_langs: Optional[set/iterable] — if provided, keep only those langs.
          keep_parent: bool — if True, also keep the original parent analyzer.
        Returns:
          list[dict] — flattened analyzers.
        """
        if allowed_langs is not None and not isinstance(allowed_langs, set):
            allowed_langs = set(allowed_langs)

        result = []
        for parent in analyzers:
            if parent.get("language_specific_containers") and isinstance(parent.get("configuration"), list):
                seen = set()
                for entry in parent["configuration"]:
                    # Each entry expected like { "python": {image: ..., ...} }
                    if not isinstance(entry, dict) or len(entry) != 1:
                        continue
                    lang, cfg = next(iter(entry.items()))
                    if allowed_langs and lang not in allowed_langs:
                        continue
                    if lang in seen:
                        # Skip duplicates; keeps the first occurrence
                        continue
                    seen.add(lang)

                    child = copy.deepcopy(parent)
                    # Remove the entire configuration from child variant
                    child.pop("configuration", None)
                    # Enforce language to the single one
                    child["language"] = [lang]
                    # Effective name for logs/IDs
                    child["name"] = f'{parent.get("name")}_{lang}'
                    # Let child config override parent fields (image, type, dockerfile_path, etc.)
                    if isinstance(cfg, dict):
                        child.update(cfg)

                    result.append(child)

                if keep_parent:
                    # Optionally keep the parent as-is (rarely needed)
                    result.append(copy.deepcopy(parent))
            else:
                # Analyzer without language-specific containers remains as-is
                result.append(copy.deepcopy(parent))

        return result

    @staticmethod
    def get_image_name(analyzer):
        return analyzer.get("image")

    @staticmethod
    def get_dockerfile_path(analyzer):
        pass

    @staticmethod
    def _filter_language_specific_config(config, allowed_langs):
        """
        Keep only configuration entries that match the allowed languages.
        Config is expected to be a list of dicts like: [{ "<lang>": { ... } }, ...].
        Removes duplicates while preserving the first occurrence.
        """
        if not isinstance(config, list):
            return []

        seen = set()
        filtered = []
        for entry in config:
            if not isinstance(entry, dict) or len(entry) != 1:
                continue
            lang, cfg = next(iter(entry.items()))
            if lang in allowed_langs and lang not in seen:
                filtered.append({lang: cfg})
                seen.add(lang)
        return filtered

    def prepare_pipeline_analyzer_config(self, languages, max_time_class="slow", target_analyzers=None) -> str:
        """
        Filters analyzers by:
          - supported languages (intersection with `languages`),
          - time_class (must be <= min_time_class),
          - optional list of target analyzer names.

        If an analyzer has `language_specific_containers=True`,
        its `configuration` is filtered so that only entries for the allowed languages remain.

        Saves the resulting analyzers list into a YAML file and returns the file path.
        """
        allowed_langs = set(languages)
        max_level = AnalyzersConfigHelper.get_level(max_time_class)
        target_set = set(target_analyzers) if target_analyzers else None

        filtered = []
        for analyzer in self.analyzers:
            langs = set(analyzer.get("language", []))
            has_lang = bool(allowed_langs & langs)
            time_ok = AnalyzersConfigHelper.get_level(analyzer.get("time_class", "slow")) <= max_level
            name_ok = True if not target_set else analyzer.get("name") in target_set

            if not (has_lang and time_ok and name_ok):
                continue

            item = copy.deepcopy(analyzer)
            if item.get("language_specific_containers"):
                item["configuration"] = AnalyzersConfigHelper._filter_language_specific_config(
                    item.get("configuration", []),
                    allowed_langs
                )
            filtered.append(item)

        filename = os.path.join(f"/tmp/sast_pipeline_{get_pipeline_id()}_analyzers_config.yml")
        with open(filename, "w", encoding="utf-8") as f:
            yaml.dump({"analyzers": filtered}, f, sort_keys=False, allow_unicode=True)

        return filename
