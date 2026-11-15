# Exports

Project exports are available as CSV or JSON. A single export includes up to 50,000 tasks; larger projects must be exported in date ranges.

Exports run as background jobs and are available for download for 7 days. A known issue causes exports started during a deploy to omit tasks changed in the final minute; re-running the export after the deploy completes avoids it.

Attachments are not included in exports. Use the API to download attachments separately.
