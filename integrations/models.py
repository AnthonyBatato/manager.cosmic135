from django.db import models

class FormCompletionEvent(models.Model):
    event_id = models.CharField(max_length=160, unique=True)
    journey = models.ForeignKey("commerce.Journey", on_delete=models.CASCADE, related_name="form_events")
    submission_id = models.CharField(max_length=160)
    completed_at = models.DateTimeField()
    received_at = models.DateTimeField(auto_now_add=True)

