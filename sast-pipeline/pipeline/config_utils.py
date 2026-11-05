import copy
import logging
import os
import textwrap
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path

import yaml

from .run_output import result_produced

log = logging.getLogger(__name__)

GENERIC_XML_SCAN_TYPE = "Generic XML Import"


class TimeClass(str, Enum):
    """How long an analyzer runs; a launch's ceiling keeps analyzers of a slower class out."""

    FAST = "fast"
    MEDIUM = "medium"
    SLOW = "slow"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def of(cls, value: object) -> "TimeClass":
        """The class ``value`` names; an unset or unknown value is the slowest class."""
        return cls(value) if value in cls._value2member_map_ else cls.SLOW


@dataclass(frozen=True)
class AnalyzerSelection:
    """
    What a SAST launch asks to run.

    The ``requested`` analyzers when any are named; otherwise every enabled analyzer for ``languages`` whose time
    class is within ``max_time_class`` (builder analyzers only for a ``compilable`` project), less ``exclude``,
    plus ``include``.
    """

    languages: tuple[str, ...] = ()
    max_time_class: TimeClass = TimeClass.SLOW
    compilable: bool = True
    requested: tuple[str, ...] = ()
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()


@dataclass(frozen=True)
class AnalyzerReport:
    """Where one configured analyzer writes its result, and which importer scan type reads it."""

    analyzer_name: str
    result_file: str
    scan_type: str

    @classmethod
    def of(cls, analyzer: dict) -> "AnalyzerReport":
        output_type = analyzer.get("output_type") or "SARIF"
        return cls(
            analyzer_name=analyzer.get("name") or "unknown",
            result_file=AnalyzersConfigHelper.get_analyzer_result_file_name(analyzer),
            scan_type=GENERIC_XML_SCAN_TYPE if output_type.lower() in {"xml", "generic-xml"} else output_type,
        )

    def path_in(self, output_dir: str | Path) -> Path:
        """Where this report is in the run's ``output_dir``."""
        return Path(output_dir) / self.result_file


class AnalyzersConfigHelper:
    SAST_EXECUTION_TYPE = "sast"
    ANALYZER_ORDER = {
        TimeClass.FAST: 0,
        TimeClass.MEDIUM: 1,
        TimeClass.SLOW: 2,
    }
    analyzers: list[dict[str, object]] = None
    languages = None

    def __init__(self, config_path=os.path.join(Path(__file__).resolve().parent, "config", "analyzers.yaml")):
        if not os.path.exists(config_path):
            raise Exception(f"Config by path {config_path} not exist")

        self.config_path = config_path
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

        log.debug(f"Analyzer config: {self.config}")

        self.analyzers = AnalyzersConfigHelper.expand_analyzers(
            self.config.get("analyzers", []),
            allowed_langs=self.languages or None
        )

    # Image names a build, the catalog name names the analyzer; the fallback follows the
    # catalog's own convention, where "sast-semgrep" is "semgrep".
    IMAGE_TOKEN_PREFIXES = ("sast-", "aist-")

    @classmethod
    def image_fallback_token(cls, image) -> str:
        """The source token an image reference alone yields, without registry, tag or digest."""
        repository = str(image).rsplit("/", 1)[-1]
        repository = repository.split("@", 1)[0].split(":", 1)[0]
        for prefix in cls.IMAGE_TOKEN_PREFIXES:
            if repository.startswith(prefix):
                return repository[len(prefix):] or repository
        return repository

    def source_token(self, image) -> str:
        """This catalog's name for ``image``, or the token its reference yields.

        Reads the raw config, not the language-expanded list, so a standalone entry resolves.
        """
        for analyzer in self.config.get("analyzers", []):
            if analyzer.get("image") == image and analyzer.get("name"):
                return str(analyzer["name"])
        return self.image_fallback_token(image)

    @classmethod
    def source_token_for_image(cls, image) -> str:
        """``source_token`` against the default catalog. Never raises."""
        helper = _default_catalog()
        return helper.source_token(image) if helper else cls.image_fallback_token(image)

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

    def get_analyzer_reports(self) -> list[AnalyzerReport]:
        return [AnalyzerReport.of(analyzer) for analyzer in self.analyzers]

    def get_produced_reports(self, output_dir: str | Path) -> list[AnalyzerReport]:
        """The configured analyzers' reports produced in ``output_dir``; an analyzer that left no result has none."""
        return [report for report in self.get_analyzer_reports() if result_produced(report.path_in(output_dir))]

    def get_supported_analyzers(self):
        if not self.analyzers:
            raise Exception("Analyzers list is empty")

        # Getting names without configurations
        supported_analyzers = list({
            analyzer.get("name")
            for analyzer in self.config.get("analyzers", [])
            if analyzer.get("enabled", True) and self._is_sast_analyzer(analyzer)
        })
        return supported_analyzers

    def get_all_images(self):
        result = set()
        for analyzer in self.analyzers:
            if self._is_sast_analyzer(analyzer):
                result.add(analyzer.get("image"))
        return result

    def get_execution_provider(self, execution_type):
        normalized_type = str(execution_type).lower()
        providers = [
            copy.deepcopy(analyzer)
            for analyzer in self.config.get("analyzers", [])
            if analyzer.get("enabled", True)
            and str(analyzer.get("execution_type", self.SAST_EXECUTION_TYPE)).lower() == normalized_type
        ]
        if len(providers) != 1:
            raise ValueError(f"Expected exactly one enabled {normalized_type} execution provider")
        return providers[0]

    def get_standalone_execution_types(self):
        return {
            str(analyzer.get("execution_type", "")).lower()
            for analyzer in self.config.get("analyzers", [])
            if analyzer.get("enabled", True)
            and analyzer.get("type") == "standalone"
            and analyzer.get("execution_type")
        }

    @classmethod
    def _is_sast_analyzer(cls, analyzer):
        return str(analyzer.get("execution_type", cls.SAST_EXECUTION_TYPE)).lower() == cls.SAST_EXECUTION_TYPE

    @staticmethod
    def convert_languages(languages):
        result = set()
        for language in languages:
            lang = language.lower().replace("#", "sharp").replace("c++", "cpp")
            result.add(lang)
        return list(result)

    def get_supported_languages(self):
        if not self.analyzers:
            raise Exception("Analyzers list is empty")

        if self.languages:
            return  self.languages

        langs_in_order = set()

        for a in self.analyzers:
            if not self._is_sast_analyzer(a):
                continue
            lang = a.get("language")
            if isinstance(lang, str):
                langs_in_order.add(lang)
            elif isinstance(lang, (list, tuple, set)):
                for x in lang:
                    if isinstance(x, str):
                        langs_in_order.add(x)

        self.languages = list(langs_in_order)

        return self.languages

    @staticmethod
    def time_class_of(analyzer: dict) -> TimeClass:
        return TimeClass.of(analyzer.get("time_class"))

    def select_analyzers(self, selection: AnalyzerSelection) -> list[str]:
        """The names of the analyzers ``selection`` runs; see :class:`AnalyzerSelection`."""
        if selection.requested:
            return list(selection.requested)
        defaults = self.get_names(
            self.get_filtered_analyzers(
                analyzers_to_run=None,
                max_time_class=selection.max_time_class,
                non_compile_project=not selection.compilable,
                target_languages=list(selection.languages),
                show_only_parent=True,
            ),
        )
        names = [name for name in defaults if name not in selection.exclude]
        names.extend(name for name in selection.include if name not in names)
        return names

    @staticmethod
    def get_names(analyzers):
        names = []
        for analyzer in analyzers:
            names.append(analyzer.get("name"))
        return names

    def get_filtered_analyzers(self, analyzers_to_run, max_time_class, non_compile_project, target_languages=None, show_only_parent=False):
        analyzers = self.config.get("analyzers", []) if show_only_parent else self.get_analyzers()
        # Filter analyzers by requested names or enabled flag
        if analyzers_to_run:
            analyzers = [
                a
                for a in analyzers
                if a.get("name") in analyzers_to_run
                and a.get("enabled", True)
                and self._is_sast_analyzer(a)
            ]
        else:
            analyzers = [a for a in analyzers if a.get("enabled", True) and self._is_sast_analyzer(a)]
        write = 0
        max_level = self.get_level(max_time_class)
        for a in analyzers:
            name = a.get("name")
            type = a.get("type", "default")
            analyzers_languages = a.get("language", [])

            if not a.get("enabled", True):
                log.debug("Disabled analyzer %s. Skipping...", name)
                continue

            if analyzers_to_run and name not in analyzers_to_run:
                log.debug("Analyzer %s not in analyzers_to_run. Skipping...", name)
                continue

            if type == "builder" and non_compile_project:
                log.warning("Attempt to launch analyzer %s on non compile project. Skipping...", name)
                continue

            if self.get_level(self.time_class_of(a)) > max_level:
                log.info("Skipping slow analyzer '%s'", name)
                continue

            if target_languages and not any(language in analyzers_languages for language in target_languages):
                log.info("Skipping not applicable by language analyzer '%s'", name)
                continue

            analyzers[write] = a

            write += 1

        del analyzers[write:]
        return analyzers

    @staticmethod
    def get_level(time_class: str | None) -> int:
        return AnalyzersConfigHelper.ANALYZER_ORDER[TimeClass.of(time_class)]

    @staticmethod
    def expand_analyzers(analyzers, allowed_langs=None):

        if allowed_langs is not None and not isinstance(allowed_langs, set):
            allowed_langs = set(allowed_langs)

        out = []

        for parent in analyzers:
            if not parent.get("enabled", True):
                log.debug(f"Skipping disabled analyzer {parent.get('name')}")
            cfg_list = parent.get("configuration")
            if not (parent.get("language_specific_containers") and isinstance(cfg_list, list)):
                out.append(copy.deepcopy(parent))
                continue

            cfg_map = {}
            for e in cfg_list:
                if isinstance(e, dict) and len(e) == 1:
                    lang, cfg = next(iter(e.items()))
                    cfg_map[lang] = dict(cfg) if isinstance(cfg, dict) else {}

            def ensure_no_extra_keys(lang, cfg):
                extra = {k for k in cfg.keys() if k not in {"inherits", "inherits_from"}}
                if extra:
                    raise ValueError(
                        f"Analyzer '{parent.get('name')}', language '{lang}': "
                        f"inherits-groups do not support overrides: unexpected keys {sorted(extra)}"
                    )

            visiting = set()
            root_cache = {}

            def get_root(lang):
                if lang in root_cache:
                    return root_cache[lang]
                if lang not in cfg_map:
                    raise ValueError(
                        f"Language '{lang}' not defined in configuration of '{parent.get('name')}'. "
                        f"'inherits' must refer to a language in the SAME configuration."
                    )
                if lang in visiting:
                    raise ValueError(f"Cycle in inherits for analyzer '{parent.get('name')}', language '{lang}'")

                visiting.add(lang)
                cfg = cfg_map[lang]
                base = cfg.get("inherits") or cfg.get("inherits_from")
                if base:
                    if base not in cfg_map:
                        raise ValueError(
                            f"Analyzer '{parent.get('name')}', language '{lang}': inherits='{base}' "
                            f"must refer to a language in the SAME configuration (not found)."
                        )

                    ensure_no_extra_keys(lang, cfg)
                    root = get_root(base)
                else:
                    root = lang
                visiting.remove(lang)
                root_cache[lang] = root
                return root

            groups = {}
            for lang in cfg_map.keys():
                root = get_root(lang)
                groups.setdefault(root, set()).add(lang)

            for root_lang, langs in groups.items():
                final_langs = list(sorted(langs if allowed_langs is None else (langs & allowed_langs)))
                if not final_langs:
                    continue

                child = copy.deepcopy(parent)
                child.pop("configuration", None)
                child.pop("language_specific_containers", None)
                child["parent"] = parent.get("name")
                child["name"] = f"{parent.get('name')}_{root_lang}"
                child["language"] = final_langs

                root_cfg = cfg_map.get(root_lang, {})
                for k, v in root_cfg.items():
                    if k !="inherits":
                        child[k] = v

                out.append(child)

        return out

    @staticmethod
    def get_image_name(analyzer):
        return analyzer.get("image")

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

    def prepare_pipeline_analyzer_config(self, languages, pipeline_id, max_time_class="slow", target_analyzers=None) -> str:
        """
        Filters analyzers by:
          - supported languages (intersection with `languages`),
          - the `target_analyzers` names when given, else time_class within `max_time_class`.

        If an analyzer has `language_specific_containers=True`,
        its `configuration` is filtered so that only entries for the allowed languages remain.

        Saves the resulting analyzers list into a YAML file and returns the file path.
        """
        allowed_langs = set(languages)
        max_level = AnalyzersConfigHelper.get_level(max_time_class)
        target_set = set(target_analyzers) if target_analyzers else None

        filtered = []
        for analyzer in self.analyzers:
            if not self._is_sast_analyzer(analyzer):
                continue
            langs = set(analyzer.get("language", []))
            has_lang = bool(allowed_langs & langs)
            time_ok = target_set is not None or self.get_level(self.time_class_of(analyzer)) <= max_level
            name_ok = True if not target_set else (
                        analyzer.get("name") in target_set or analyzer.get("parent") in target_set)

            if not (has_lang and time_ok and name_ok):
                continue

            item = copy.deepcopy(analyzer)
            if item.get("language_specific_containers"):
                item["configuration"] = AnalyzersConfigHelper._filter_language_specific_config(
                    item.get("configuration", []),
                    allowed_langs
                )
            filtered.append(item)

        os.makedirs("/tmp/aist/tmp/", exist_ok=True)
        filename = os.path.join(f"/tmp/aist/tmp/sast_pipeline_{pipeline_id}_analyzers_config.yml")
        with open(filename, "w", encoding="utf-8") as f:
            yaml.dump({"analyzers": filtered}, f, sort_keys=False, allow_unicode=True)

        return filename

    def pretty_print(self, max_width: int = 80) -> str:
        """
        Produce a Markdown-friendly table with analyzers info and stats.

        Iterates over `self.analyzers` (already flattened list of analyzer variants).

        Markdown table columns:
          | # | Name | Langs | InBuild | Enabled | Comment |
            - #: row number
            - Name: analyzer name (aggregated across variants)
            - Langs: comma-separated languages
            - InBuild: "yes" if any variant has type == "builder"
            - Enabled: yes / no / partial (aggregated)
            - Comment: joined comments, truncated/wrapped

        Stats:
          - Total analyzers
          - Enabled analyzers
          - Disabled analyzers
          - InBuild analyzers
          - Per-language: enabled/total
        """
        variants = list(getattr(self, "analyzers", []) or [])

        def _to_list(x):
            if x is None:
                return []
            if isinstance(x, (list, tuple, set)):
                return [str(i) for i in x]
            return [str(x)]

        by_name = {}
        per_lang = {}

        for v in variants:
            name = str(v.get("name", ""))
            langs = _to_list(v.get("language")) or ["unknown"]
            enabled = bool(v.get("enabled", True))
            is_builder = str(v.get("type", "")).lower() == "builder"
            comments = [s.strip() for s in _to_list(v.get("commentary")) if str(s).strip()]

            g = by_name.setdefault(name, {
                "languages": set(),
                "any_enabled": False,
                "all_enabled": True,
                "any_inbuild": False,
                "comments": set(),
            })
            for lang in langs:
                g["languages"].add(lang)
            g["any_enabled"] = g["any_enabled"] or enabled
            g["all_enabled"] = g["all_enabled"] and enabled
            g["any_inbuild"] = g["any_inbuild"] or is_builder
            for c in comments:
                g["comments"].add(c)

            # per-language counters
            for lang in set(langs):
                d = per_lang.setdefault(lang, {"total": 0, "enabled": 0})
                d["total"] += 1
                if enabled:
                    d["enabled"] += 1

        def _enabled_str(group):
            if group["all_enabled"]:
                return "yes"
            if not group["any_enabled"]:
                return "no"
            return "partial"

        # Build Markdown table rows with numbering
        headers = ["#", "Name", "Langs", "InBuild", "Enabled", "Comment"]
        md_lines = []
        md_lines.append("| " + " | ".join(headers) + " |")
        md_lines.append("|" + "|".join(["---"] * len(headers)) + "|")

        for idx, name in enumerate(sorted(by_name.keys(), key=lambda s: s.lower()), 1):
            g = by_name[name]
            langs = ", ".join(sorted(g["languages"]))
            inbuild = "yes" if g["any_inbuild"] else "no"
            enabled_s = _enabled_str(g)
            comment_joined = "; ".join(sorted(g["comments"])) if g["comments"] else ""
            comment_wrapped = textwrap.shorten(comment_joined, width=max_width, placeholder="…")
            row = [str(idx), name, langs, inbuild, enabled_s, comment_wrapped]
            md_lines.append("| " + " | ".join(row) + " |")

        # Stats
        total_analyzers = len(by_name)
        enabled_analyzers = sum(1 for g in by_name.values() if g["any_enabled"])
        disabled_analyzers = total_analyzers - enabled_analyzers
        inbuild_analyzers = sum(1 for g in by_name.values() if g["any_inbuild"])

        stats_lines = []
        stats_lines.append("")
        stats_lines.append("**Stats:**")
        stats_lines.append(f"- Total analyzers: {total_analyzers}")
        stats_lines.append(f"- Enabled: {enabled_analyzers}")
        stats_lines.append(f"- Disabled: {disabled_analyzers}")
        stats_lines.append(f"- InBuild analyzers: {inbuild_analyzers}")
        stats_lines.append("- Per-language:")
        for lang in sorted(per_lang.keys()):
            s = per_lang[lang]
            stats_lines.append(f"  - {lang}: {s['enabled']}/{s['total']} enabled")

        return "\n".join(md_lines + stats_lines)

@lru_cache(maxsize=1)
def _default_catalog():
    """The packaged catalog, loaded once, or None when it cannot be read."""
    try:
        return AnalyzersConfigHelper()
    except Exception:
        log.warning("Analyzer catalog unavailable; source tokens fall back to the image reference")
        return None


if __name__ == "__main__":
    helper = AnalyzersConfigHelper("config/analyzers.yaml")
    print(helper.pretty_print(80))
