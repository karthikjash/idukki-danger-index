"""Mobile SMS alert service for the Idukki Danger Index.

Subscriptions (store.py) -> per-plan message composition (messages.py) ->
SMS delivery (sms.py, real gateway when configured, honest demo outbox
otherwise) -> background evaluation loop (scheduler.py).

Subscription plans a resident can choose:
  * danger  - instant alert when a chosen panchayat crosses the threshold
  * daily   - 07:00 IST briefing: today's reading + tomorrow's forecast
  * weekly  - Monday 08:00 IST outlook: the week's worst day per area
"""
