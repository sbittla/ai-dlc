# Dates and Time Zones

Relay stores all timestamps in UTC and converts them to the viewer's time zone for display. Due dates without a time are stored as dates, not timestamps.

A known defect affects users in time zones more than 12 hours ahead of UTC, such as Pacific/Auckland during daylight saving: due dates can display one day early. The fix is scheduled for the 4.18 release.

Recurring tasks use the time zone of the person who created the recurrence, not the assignee.
