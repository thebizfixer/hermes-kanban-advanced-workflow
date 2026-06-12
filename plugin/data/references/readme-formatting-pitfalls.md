# README formatting pitfalls

Check after editing `README.md` or large markdown exports.

| Pitfall | Detection | Fix |
|---------|-----------|-----|
| URL-encoded HTML wrappers | `%3Cdiv%3E`, `%3C/` in source | Decode; use plain markdown |
| HTML entities in prose | `&gt;`, `&lt;`, `&amp;` | Replace with literal characters |
| Broken code fences | Odd line count of ` ``` ` | Close fences; language tag on open only |
| Triple+ blank lines | `\n\n\n\n` | Collapse to one blank line |
| Mixed list + table | List item wraps table row | Separate with blank line; fix pipe alignment |
| User prose rewritten | Diff shows unsolicited tone change | Revert; only fix factual errors |

Run `documentation-sanity-check.md` link scan after bulk edits.
