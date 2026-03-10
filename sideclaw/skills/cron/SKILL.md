---
summary: "Schedule recurring reminders and agent tasks with the cron tool"
read_when:
  - recurring reminder
  - schedule a weekly task
  - every friday
  - every week
  - remind me later
  - cron job
tags:
  - cron
  - schedule
  - reminder
  - recurring
status: active
---

# Cron Skill

Use the `cron` tool when the user wants something to happen again later or on a repeating schedule.

## Default behavior

- Use the current chat as the delivery target.
- Persist the job so it continues when `sideclaw gateway` is running.
- If the user says "every Friday night at 9pm", convert it to a cron schedule.
- Unless the user specifies a timezone, assume the server's local timezone.

## Common mappings

- every day at 9am -> `0 9 * * *`
- every Friday at 9pm -> `0 21 * * 5`
- weekdays at 6pm -> `0 18 * * 1-5`
- every first day of the month at 8am -> `0 8 1 * *`

## Tool usage

Add:
```text
cron(action="add", prompt="Send me a new meal plan", schedule="0 21 * * 5", name="weekly meal plan")
```

List:
```text
cron(action="list")
```

Remove:
```text
cron(action="remove", job_id="<job-id>")
```

Disable or enable:
```text
cron(action="disable", job_id="<job-id>")
cron(action="enable", job_id="<job-id>")
```
