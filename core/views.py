from django.shortcuts import render, redirect
from django import forms
from .models import Domain, Drop, Competitor
from django.db.models import F

from django.utils import timezone
from django.contrib.auth.decorators import login_required
import random

# Create your views here.

TLD_CHOICES = ["com", "net", "org", "uk", "eu", "info", "io", "co"]

class DomainForm(forms.ModelForm):
    class Meta:
        model = Domain
        fields = ["name", "tld"]

class RandomDomainForm(forms.Form):
    count = forms.IntegerField(min_value=1, max_value=100, initial=5, label="Number of random domains")
    clear_after_minutes = forms.IntegerField(min_value=1, max_value=60, initial=5, label="Clear After (minutes)")

class CompetitorForm(forms.Form):
    drop = forms.ModelChoiceField(queryset=Drop.objects.all())
    name = forms.CharField(max_length=255)
    attempts = forms.IntegerField(min_value=1, initial=1)

@login_required
def dashboard(request):
    domain_form = DomainForm()
    random_form = RandomDomainForm()
    competitor_form = CompetitorForm()
    message = None

    if request.method == "POST":
        if "add_domain" in request.POST:
            domain_form = DomainForm(request.POST)
            if domain_form.is_valid():
                domain = domain_form.save()
                # Set drop_time to 2 minutes after the latest drop or now
                last_drop = Drop.objects.order_by('-drop_time').first()
                base_time = last_drop.drop_time if last_drop else timezone.now()
                drop_time = base_time + timezone.timedelta(minutes=2)
                Drop.objects.create(domain=domain, drop_time=drop_time)
                message = "Domain added and ready for catch."
        elif "generate_domains" in request.POST:
            random_form = RandomDomainForm(request.POST)
            if random_form.is_valid():
                count = random_form.cleaned_data["count"]
                clear_after = random_form.cleaned_data["clear_after_minutes"]
                # Find the latest drop_time or now
                last_drop = Drop.objects.order_by('-drop_time').first()
                base_time = last_drop.drop_time if last_drop else timezone.now()
                for i in range(count):
                    name = "domain" + str(random.randint(10000, 99999))
                    tld = random.choice(TLD_CHOICES)
                    domain = Domain.objects.create(name=name, tld=tld)
                    drop_time = base_time + timezone.timedelta(minutes=2 * (i + 1))
                    Drop.objects.create(domain=domain, drop_time=drop_time, clear_after_minutes=clear_after)
                message = f"{count} random domains generated and ready for catch."
        elif "edit_drop_time" in request.POST:
            drop_id = request.POST.get('drop_id')
            new_time = request.POST.get('new_drop_time')
            if drop_id and new_time:
                try:
                    drop = Drop.objects.get(id=drop_id)
                    # Parse the new time as an aware datetime
                    from django.utils.dateparse import parse_datetime
                    parsed_time = parse_datetime(new_time)
                    if parsed_time:
                        drop.drop_time = parsed_time
                        drop.save()
                        message = "Drop time updated."
                    else:
                        message = "Invalid date/time format."
                except Drop.DoesNotExist:
                    message = "Drop not found."
        elif "edit_competitor_delay" in request.POST:
            competitor_id = request.POST.get('competitor_id')
            new_delay = request.POST.get('new_delay_ms')
            if competitor_id and new_delay is not None:
                try:
                    comp = Competitor.objects.get(id=competitor_id)
                    comp.delay_ms = int(new_delay)
                    comp.save()
                    message = f"Delay updated for {comp.name}."
                except Competitor.DoesNotExist:
                    message = "Competitor not found."
        elif "add_competitor" in request.POST:
            competitor_form = CompetitorForm(request.POST)
            if competitor_form.is_valid():
                drop = competitor_form.cleaned_data["drop"]
                name = competitor_form.cleaned_data["name"]
                attempts = competitor_form.cleaned_data["attempts"]
                Competitor.objects.create(drop=drop, name=name, attempts=attempts)
                message = "Competitor added."

    domains = Domain.objects.all().order_by("-created_at")[:20]
    now = timezone.now()
    drops = Drop.objects.filter(
        drop_time__gt=now - F('clear_after_minutes') * 60
    ).order_by("-created_at")[:20]
    competitors = Competitor.objects.all().order_by("-created_at")[:20]

    return render(request, "core/dashboard.html", {
        "domain_form": domain_form,
        "random_form": random_form,
        "competitor_form": competitor_form,
        "domains": domains,
        "drops": drops,
        "competitors": competitors,
        "message": message,
    })
