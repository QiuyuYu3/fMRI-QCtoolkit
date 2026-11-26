"""Check that the tag, pyproject.toml, CITATION.cff and CHANGELOG.md agree, then write the release notes."""

import re
import sys
import tomllib
from pathlib import Path


def changelog_sections(lines):
    heads = [(i, m.group(1), m.group(2)) for i, line in enumerate(lines)
             if (m := re.match(r"## \[(.+?)\](?: - (\S+))?\s*$", line))]
    ends = [i for i, _, _ in heads[1:]] + [len(lines)]
    return [(name, date, "\n".join(lines[i + 1:end]).strip()) for (i, name, date), end in zip(heads, ends)]


def check(tag, today):
    errors = []
    version = tag.removeprefix("v")

    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    if pyproject != version:
        errors.append(f"pyproject.toml has version {pyproject}, the tag is {tag}.")

    citation = Path("CITATION.cff").read_text(encoding="utf-8")
    cff_version = re.search(r"^version:\s*\"?([^\s\"]+)", citation, re.M)
    cff_date = re.search(r"^date-released:\s*\"?([^\s\"]+)", citation, re.M)
    if not cff_version or cff_version.group(1) != version:
        errors.append(f"CITATION.cff has version {cff_version and cff_version.group(1)}, the tag is {tag}.")
    if not cff_date or cff_date.group(1) != today:
        errors.append(f"CITATION.cff has date-released {cff_date and cff_date.group(1)}, today is {today}.")

    sections = changelog_sections(Path("CHANGELOG.md").read_text(encoding="utf-8").splitlines())
    if sections and sections[0][0] == "Unreleased" and sections[0][2]:
        errors.append("CHANGELOG.md has entries under [Unreleased]; move them into this version.")
    released = [s for s in sections if s[0] != "Unreleased"]
    notes = ""
    if not released:
        errors.append("CHANGELOG.md has no version section.")
    else:
        name, date, notes = released[0]
        if name != version:
            errors.append(f"The first version in CHANGELOG.md is {name}, the tag is {tag}.")
        if date != today:
            errors.append(f"CHANGELOG.md dates {name} {date}, today is {today}.")
    return errors, notes


def main():
    tag, today, notes_path = sys.argv[1:4]
    errors, notes = check(tag, today)
    for error in errors:
        print(f"::error::{error}")
    if errors:
        sys.exit(1)
    Path(notes_path).write_text(notes + "\n", encoding="utf-8")
    print(f"{tag} matches pyproject.toml, CITATION.cff and CHANGELOG.md, dated {today}.")


if __name__ == "__main__":
    main()
