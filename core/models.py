from django.db import models

# Create your models here.

class Domain(models.Model):
    name = models.CharField(max_length=255, unique=True)
    tld = models.CharField(max_length=20)  # e.g., com, uk, eu, etc.
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name}.{self.tld}"

class Drop(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("captured", "Captured"),
        ("missed", "Missed"),
    ]
    domain = models.ForeignKey(Domain, on_delete=models.CASCADE, related_name='drops')
    drop_time = models.DateTimeField()
    clear_after_minutes = models.PositiveIntegerField(default=5)  # Minutes after drop to clear domain
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="pending")
    winner = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"Drop for {self.domain} at {self.drop_time}"

class Competitor(models.Model):
	# ...existing code...
    drop = models.ForeignKey(Drop, on_delete=models.CASCADE, related_name='competitors')
    name = models.CharField(max_length=255)
    attempts = models.PositiveIntegerField(default=0)
    delay_ms = models.PositiveIntegerField(default=100)  # Simulated network delay in milliseconds
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} (Drop: {self.drop})"
