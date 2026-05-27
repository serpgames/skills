#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"
DOCS_DIR = ROOT / "docs"
DEFAULT_ORG = "serpgames"

EXCLUDED_REPOS = {
    ".github",
    "images",
    "serpgames.github.io",
    "serpgames-platform",
    "skills",
}


def run_gh(args: list[str]) -> str:
    result = subprocess.run(
        ["gh", *args],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout


def slug_to_title(slug: str) -> str:
    base = slug.removesuffix("-game")
    return " ".join(part.upper() if part.isdigit() else part.capitalize() for part in base.split("-"))


def repo_to_game_id(repo_name: str) -> str:
    return repo_name.removesuffix("-game")


def yaml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def should_include_repo(repo: dict[str, Any]) -> bool:
    if repo["name"] in EXCLUDED_REPOS:
        return False
    if repo["isPrivate"] or repo["isArchived"] or repo["isFork"]:
        return False
    return repo["name"].endswith("-game")


def fetch_repos(org: str = DEFAULT_ORG) -> list[dict[str, Any]]:
    payload = run_gh(
        [
            "repo",
            "list",
            org,
            "--limit",
            "500",
            "--json",
            "name,description,isPrivate,isArchived,isFork,url,pushedAt",
        ]
    )
    repos = json.loads(payload)
    return sorted((repo for repo in repos if should_include_repo(repo)), key=lambda repo: repo["name"])


def fetch_readme(repo_name: str, org: str = DEFAULT_ORG) -> str | None:
    result = subprocess.run(
        [
            "gh",
            "api",
            f"repos/{org}/{repo_name}/readme",
            "-H",
            "Accept: application/vnd.github.raw+json",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    if result.returncode == 0:
        return result.stdout
    if "Not Found" in result.stderr or "HTTP 404" in result.stderr:
        return None
    result.check_returncode()
    return None


def platform_config_path() -> Path:
    configured = os.environ.get("SERPGAMES_PLATFORM_ROOT")
    if configured:
        return Path(configured) / "games-config.yaml"
    return ROOT.parent / "serpgames-platform" / "games-config.yaml"


def load_platform_metadata() -> dict[str, dict[str, Any]]:
    config_path = platform_config_path()
    if not config_path.exists():
        return {}

    try:
        import yaml  # type: ignore
    except ImportError:
        return {}

    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        return {}

    by_repo: dict[str, dict[str, Any]] = {}
    for game_id, meta in data.items():
        if not isinstance(meta, dict):
            continue

        repo_url = str(meta.get("repository") or "")
        match = re.search(r"github\.com/serpgames/([^/\s]+)", repo_url)
        repo_name = match.group(1) if match else f"{game_id}-game"
        by_repo[repo_name] = meta

    return by_repo


def normalize_relative_target(target: str) -> str:
    while target.startswith("./"):
        target = target[2:]
    return target.lstrip("/")


def absolutize_relative_paths(text: str, repo_name: str, org: str = DEFAULT_ORG) -> str:
    raw_base = f"https://raw.githubusercontent.com/{org}/{repo_name}/refs/heads/main/"

    def is_relative(target: str) -> bool:
        if not target:
            return False
        if target.startswith(("#", "http://", "https://", "mailto:", "data:")):
            return False
        return True

    def replace_markdown(match: re.Match[str]) -> str:
        target = match.group(1).strip()
        suffix = match.group(2) or ""
        if not is_relative(target):
            return match.group(0)
        return f"]({raw_base}{normalize_relative_target(target)}{suffix})"

    def replace_html_attr(match: re.Match[str]) -> str:
        attr = match.group(1)
        quote = match.group(2)
        target = match.group(3).strip()
        if not is_relative(target):
            return match.group(0)
        return f'{attr}={quote}{raw_base}{normalize_relative_target(target)}{quote}'

    text = re.sub(r"\]\(([^)\s]+)(\s+\"[^\"]*\")?\)", lambda match: replace_markdown(match), text)
    text = re.sub(r'(src|href)=(["\'])([^"\']+)\2', lambda match: replace_html_attr(match), text)
    return text


def clean_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    cleaned: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text.lower() not in {"instruction 1", "instruction 2"}:
            cleaned.append(text)
    return cleaned


def build_fallback_body(repo: dict[str, Any], metadata: dict[str, Any] | None) -> str:
    metadata = metadata or {}
    repo_name = repo["name"]
    game_id = repo_to_game_id(repo_name)
    game_name = str(metadata.get("name") or slug_to_title(repo_name))
    description = str(metadata.get("description") or repo.get("description") or f"Play {game_name} online.")
    category = str(metadata.get("category") or "browser game")
    tags = clean_list(metadata.get("tags"))
    controls = clean_list(metadata.get("controls"))
    how_to_play = clean_list(metadata.get("howToPlay"))
    play_url = str(metadata.get("gameUrl") or f"https://games.serp.co/games/{game_id}/")
    repository = str(metadata.get("repository") or repo.get("url") or f"https://github.com/serpgames/{repo_name}")

    if not controls:
        controls = ["Keyboard, mouse, or touch controls, depending on the game"]
    if not how_to_play:
        how_to_play = [
            f"Open the canonical {game_name} play page on SERP Games.",
            "Start the browser game with no download or install.",
            "Use the listed controls to play the game.",
            "Replay to improve your score, timing, or route.",
        ]

    tag_text = ", ".join(tags) if tags else category
    lines = [
        f"# Play {game_name} Game Online - Free Unblocked",
        "",
        f"Play {game_name} online free in your browser on SERP Games. {description}",
        "",
        f"## {game_name} Game Overview",
        "",
        f"{game_name} is a {category} game available from SERP Games. Use the canonical play link to launch the game with no download or install.",
        "",
        "## Game Details",
        "",
        "| Feature | Details |",
        "| --- | --- |",
        f"| Game | {game_name} |",
        f"| Category | {category} |",
        f"| Tags | {tag_text} |",
        "| Platform | Browser |",
        "| Download required | No |",
        f"| Play page | {play_url} |",
        f"| Repository | {repository} |",
        "",
        f"## How to Play {game_name}",
        "",
    ]

    lines.extend(f"- {step}" for step in how_to_play)
    lines.extend(["", "## Controls", ""])
    lines.extend(f"- {control}" for control in controls)
    lines.extend(
        [
            "",
            "## Why Play on SERP Games?",
            "",
            f"- Play {game_name} online from a direct browser page.",
            "- No download, launcher, or install is required.",
            "- The game page is built for quick access to free unblocked browser games.",
            "- SERP Games keeps the canonical play URL in one easy-to-share place.",
            "",
            "## Play Now",
            "",
            f"Start here: [Play {game_name} online free unblocked]({play_url}).",
            "",
            "## Support and Project Links",
            "",
            f"- [{game_name} on SERP Games]({play_url})",
            f"- [{repo_name} on GitHub]({repository})",
        ]
    )

    return "\n".join(lines)


def build_skill_doc(
    repo: dict[str, Any],
    readme: str | None,
    platform_metadata: dict[str, dict[str, Any]],
    org: str = DEFAULT_ORG,
) -> tuple[str, str]:
    description = (repo.get("description") or "").strip()
    if not description:
        description = f"Play {slug_to_title(repo['name'])} online free unblocked on SERP Games."

    if readme is None:
        content = build_fallback_body(repo, platform_metadata.get(repo["name"]))
        readme_source = "metadata-fallback"
    else:
        content = readme.lstrip("\ufeff").strip()
        content = absolutize_relative_paths(content, repo["name"], org)
        readme_source = "readme"

    doc = (
        "---\n"
        f"name: {repo['name']}\n"
        f"description: {yaml_string(description)}\n"
        "---\n\n"
        f"{content.strip()}\n"
    )
    return doc, readme_source


def main() -> None:
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    repos = fetch_repos(DEFAULT_ORG)
    platform_metadata = load_platform_metadata()
    manifest: list[dict[str, str]] = []

    for repo in repos:
        repo_name = repo["name"]
        readme = fetch_readme(repo_name, DEFAULT_ORG)
        doc, readme_source = build_skill_doc(repo, readme, platform_metadata, DEFAULT_ORG)

        skill_dir = SKILLS_DIR / repo_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(doc, encoding="utf-8")

        manifest.append(
            {
                "repo": repo_name,
                "skill": repo_name,
                "url": repo["url"],
                "pushedAt": repo["pushedAt"],
                "source": f"{DEFAULT_ORG}/{repo_name}",
                "readmeSource": readme_source,
            }
        )

    (DOCS_DIR / "serpgames-live-games.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Synced {len(manifest)} skills")


if __name__ == "__main__":
    main()
