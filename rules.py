from __future__ import annotations

from pathlib import Path

import yaml

from schemas import DepartmentPreferences, DepartmentProfile, DepartmentRulesConfig


class RuleLoadError(ValueError):
    pass


def load_department_rules(raw_yaml: str) -> DepartmentRulesConfig:
    if not raw_yaml.strip():
        raise RuleLoadError("Department rules YAML is required.")

    try:
        payload = yaml.safe_load(raw_yaml) or {}
    except yaml.YAMLError as exc:
        raise RuleLoadError("Invalid department rules YAML.") from exc

    if not isinstance(payload, dict):
        raise RuleLoadError("Department rules YAML must define an object.")

    config = DepartmentRulesConfig.model_validate(payload)
    if not config.profiles:
        raise RuleLoadError("Department rules YAML must define at least one profile.")
    if config.default_profile not in config.profiles:
        raise RuleLoadError(f"Default profile '{config.default_profile}' was not found in profiles.")
    return config


def load_department_rules_file(path: str = "department_rules.yaml") -> DepartmentRulesConfig:
    try:
        raw_yaml = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise RuleLoadError(f"Could not read department rules file: {path}") from exc
    return load_department_rules(raw_yaml)


def resolve_department_profile(
    config: DepartmentRulesConfig,
    department_profile: str | None,
) -> tuple[str, DepartmentProfile]:
    profile_name = department_profile or config.default_profile
    profile = config.profiles.get(profile_name)
    if profile is None:
        available = ", ".join(sorted(config.profiles))
        raise RuleLoadError(
            f"Department profile '{profile_name}' was not found. Available profiles: {available}"
        )
    return profile_name, profile


def load_department_preferences(raw_input: str | dict | None) -> DepartmentPreferences:
    if not raw_input:
        return DepartmentPreferences()
    if isinstance(raw_input, dict):
        return DepartmentPreferences.model_validate(raw_input)
    raw_text = str(raw_input).strip()
    if not raw_text:
        return DepartmentPreferences()
    try:
        payload = yaml.safe_load(raw_text) or {}
    except yaml.YAMLError as exc:
        raise RuleLoadError("Invalid department preference YAML.") from exc
    if isinstance(payload, str):
        return DepartmentPreferences(
            preferred_backgrounds=[raw_text],
            preferred_traits=[raw_text],
        )
    if isinstance(payload, (int, float, bool)):
        return DepartmentPreferences(
            preferred_backgrounds=[raw_text],
            preferred_traits=[raw_text],
        )
    if not isinstance(payload, dict):
        return DepartmentPreferences(
            preferred_backgrounds=[raw_text],
            preferred_traits=[raw_text],
        )
    return DepartmentPreferences.model_validate(payload)
