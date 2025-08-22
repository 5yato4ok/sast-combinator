import yaml
import os
import copy
import logging
import textwrap
from docker_utils import get_pipeline_id

log = logging.getLogger(__name__)


class AnalyzersConfigHelper:
    ANALYZER_ORDER = {
        "fast": 0,
        "medium": 1,
        "slow": 2,
    }
    analyzers: list[dict[str, object]] = None
    languages = None

    def __init__(self, config_path, ):
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

        # Getting names without configurations
        supported_analyzers = list({analyzer.get("name")
                                    for analyzer in self.config.get("analyzers", []) if analyzer.get("enabled", True)})
        return supported_analyzers

    def get_all_images(self):
        result = set()
        for analyzer in self.analyzers:
            result.add(analyzer.get("image"))
        return result

    def get_supported_languages(self):
        if not self.analyzers:
            raise Exception("Analyzers list is empty")

        if self.languages:
            return  self.languages

        langs_in_order = set()

        for a in self.analyzers:
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
    def get_level(time_class: str) -> int:
        return AnalyzersConfigHelper.ANALYZER_ORDER.get(time_class, 100)

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

        filename = os.path.join(f"/tmp/sast_pipeline_{get_pipeline_id()}_analyzers_config.yml")
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

if __name__ == "__main__":
    helper = AnalyzersConfigHelper("config/analyzers.yaml")
    print(helper.pretty_print(80))
