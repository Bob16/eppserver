from django.contrib import admin
from .models import Domain, Drop, Competitor

@admin.register(Domain)
class DomainAdmin(admin.ModelAdmin):
    list_display = ("name", "tld", "created_at")
    search_fields = ("name", "tld")

@admin.register(Drop)
class DropAdmin(admin.ModelAdmin):
    list_display = ("domain", "drop_time", "created_at")
    search_fields = ("domain__name",)
    list_filter = ("drop_time",)

@admin.register(Competitor)
class CompetitorAdmin(admin.ModelAdmin):
    list_display = ("name", "drop", "attempts", "created_at")
    search_fields = ("name", "drop__domain__name")
    list_filter = ("drop",)
