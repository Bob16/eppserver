from django.core.serializers.json import DjangoJSONEncoder
from django.utils.timesince import timesince
# API endpoint for recent drops (JSON)
from django.contrib.auth.decorators import login_required as _login_required
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_GET
@require_GET
@_login_required
def api_recent_drops(request):
    # --- Automatic capture logic (same as dashboard) ---
    from django.utils import timezone
    from django.db import transaction
    now = timezone.now()
    with transaction.atomic():
        for drop in Drop.objects.select_for_update().filter(status="pending", drop_time__lte=now):
            competitors = list(drop.competitors.all())
            if competitors:
                winner = min(competitors, key=lambda c: c.delay_ms)
                drop.status = "captured"
                drop.winner = winner.name
                drop.save()
            else:
                clear_time = drop.drop_time + timezone.timedelta(minutes=drop.clear_after_minutes)
                if now >= clear_time:
                    drop.status = "missed"
                    drop.winner = None
                    drop.save()
    sort = request.GET.get("sort", "drop_time")
    order = request.GET.get("order", "asc")
    if sort not in ("drop_time", "created_at"): sort = "drop_time"
    if order not in ("asc", "desc"): order = "asc"
    sort_prefix = "" if order == "asc" else "-"
    drops = Drop.objects.order_by(f"{sort_prefix}{sort}")[:20]
    my_name = request.user.username if request.user.is_authenticated else None
    drop_list = []
    import pytz
    from django.conf import settings
    # Use BST (Europe/London with DST)
    tz = pytz.timezone("Europe/London")
    for drop in drops:
        if drop.status == "captured" and drop.winner != my_name:
            drop_status = "missed"
        elif drop.status == "captured" and drop.winner == my_name:
            drop_status = "captured"
        else:
            drop_status = drop.status
        drop_time_bst = drop.drop_time.astimezone(tz)
        created_at_bst = drop.created_at.astimezone(tz)
        # For datetime-local input: yyyy-MM-ddTHH:mm:ss
        drop_time_iso = drop_time_bst.strftime("%Y-%m-%dT%H:%M:%S")
        drop_list.append({
            "id": drop.id,
            "domain": str(drop.domain),
            "drop_time": drop_time_bst.strftime("%I:%M:%S %p"),
            "drop_time_iso": drop_time_iso,
            "created_at": created_at_bst.strftime("%I:%M:%S %p"),
            "status": drop_status,
            "winner": drop.winner or "-",
            "competitors": [
                {"name": c.name, "attempts": c.attempts, "delay_ms": c.delay_ms}
                for c in drop.competitors.all()
            ]
        })
    import json
    return HttpResponse(json.dumps({"drops": drop_list}), content_type="application/json")
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
import os
# ...existing code...

# API endpoint for external capture requests
@csrf_exempt
def api_capture(request):
        if request.method != "POST":
                return HttpResponse("""
<epp>
    <response>
        <result code="2001">
            <msg>POST required</msg>
        </result>
    </response>
</epp>
""", content_type="application/xml", status=405)
        api_token = os.environ.get("DOMAIN_CAPTURE_API_TOKEN")
        auth = request.headers.get("Authorization", "").replace("Token ", "")
        if not api_token or auth != api_token:
                return HttpResponse("""
<epp>
    <response>
        <result code="2200">
            <msg>Unauthorized</msg>
        </result>
    </response>
</epp>
""", content_type="application/xml", status=401)
        from xml.etree import ElementTree as ET
        try:
                xml = ET.fromstring(request.body.decode())
                command = xml.find("command")
                if command is None:
                        raise Exception("Missing <command>")
                capture = command.find("capture")
                if capture is None:
                        raise Exception("Missing <capture>")
                drop_id = int(capture.findtext("drop:id"))
                name = capture.findtext("drop:name")
                attempts = int(capture.findtext("drop:attempts") or 1)
                delay_ms = int(capture.findtext("drop:delay_ms") or 100)
        except Exception as e:
                return HttpResponse(f"""
<epp>
    <response>
        <result code="2002">
            <msg>Invalid input: {e}</msg>
        </result>
    </response>
</epp>
""", content_type="application/xml", status=400)
        try:
                drop = Drop.objects.get(id=drop_id)
                if drop.status != "pending":
                        return HttpResponse("""
<epp>
    <response>
        <result code="2304">
            <msg>Drop is not pending.</msg>
        </result>
    </response>
</epp>
""", content_type="application/xml", status=400)
                comp = Competitor.objects.create(drop=drop, name=name, attempts=attempts, delay_ms=delay_ms)
                return HttpResponse(f"""
<epp>
    <response>
        <result code="1000">
            <msg>Command completed successfully</msg>
        </result>
        <resData>
            <drop:competitor_id>{comp.id}</drop:competitor_id>
        </resData>
    </response>
</epp>
""", content_type="application/xml")
        except Drop.DoesNotExist:
                return HttpResponse("""
<epp>
    <response>
        <result code="2303">
            <msg>Drop not found.</msg>
        </result>
    </response>
</epp>
""", content_type="application/xml", status=404)
from django.shortcuts import render, redirect
from django import forms
from .models import Domain, Drop, Competitor
from django.db.models import F

from django.utils import timezone
from django.db import transaction
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

    # --- Automatic capture logic ---
    now = timezone.now()
    my_name = request.user.username if request.user.is_authenticated else None
    with transaction.atomic():
        for drop in Drop.objects.select_for_update().filter(status="pending", drop_time__lte=now):
            competitors = list(drop.competitors.all())
            if competitors:
                winner = min(competitors, key=lambda c: c.delay_ms)
                drop.status = "captured"
                drop.winner = winner.name
            else:
                drop.status = "missed"
                drop.winner = None
            drop.save()

    # Sorting logic for drops
    sort = request.GET.get("sort", "drop_time")
    order = request.GET.get("order", "asc")
    if sort not in ("drop_time", "created_at"): sort = "drop_time"
    if order not in ("asc", "desc"): order = "asc"
    sort_prefix = "" if order == "asc" else "-"
    drops = list(Drop.objects.order_by(f"{sort_prefix}{sort}")[:20])
    for drop in drops:
        if drop.status == "captured" and drop.winner != my_name:
            drop.status = "missed"
            drop.save(update_fields=["status"])
            drop.display_status = "missed"
        elif drop.status == "captured" and drop.winner == my_name:
            drop.display_status = "captured"
        else:
            drop.display_status = drop.status

    if request.method == "POST":
        if "remove_missed_drops" in request.POST:
            removed_count, _ = Drop.objects.filter(status="missed").delete()
            message = f"Removed {removed_count} missed drops."
        elif "add_domain" in request.POST:
            domain_form = DomainForm(request.POST)
            if domain_form.is_valid():
                domain = domain_form.save()
                last_drop = Drop.objects.order_by('-drop_time').first()
                base_time = last_drop.drop_time if last_drop else timezone.now()
                drop_time = base_time + timezone.timedelta(minutes=2)
                Drop.objects.create(domain=domain, drop_time=drop_time)
                message = "Domain added and ready for catch."
            # Refresh drops list after add
            drops = list(Drop.objects.order_by("-created_at")[:20])
        elif "generate_domains" in request.POST:
            random_form = RandomDomainForm(request.POST)
            if random_form.is_valid():
                count = random_form.cleaned_data["count"]
                clear_after = random_form.cleaned_data["clear_after_minutes"]
                last_drop = Drop.objects.order_by('-drop_time').first()
                base_time = last_drop.drop_time if last_drop else timezone.now()
                for i in range(count):
                    name = "domain" + str(random.randint(10000, 99999))
                    tld = random.choice(TLD_CHOICES)
                    domain = Domain.objects.create(name=name, tld=tld)
                    drop_time = base_time + timezone.timedelta(minutes=2 * (i + 1))
                    Drop.objects.create(domain=domain, drop_time=drop_time, clear_after_minutes=clear_after)
                message = f"{count} random domains generated and ready for catch."
            # Refresh drops list after generate
            drops = list(Drop.objects.order_by("-created_at")[:20])
        elif "edit_drop_time" in request.POST:
            drop_id = request.POST.get('drop_id')
            new_time = request.POST.get('new_drop_time')
            if drop_id and new_time:
                try:
                    drop = Drop.objects.get(id=drop_id)
                    if drop.status != "pending":
                        message = "Cannot edit drop time for captured/missed drops."
                    else:
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
                    if comp.drop.status != "pending":
                        message = "Cannot edit competitor for captured/missed drops."
                    else:
                        comp.delay_ms = int(new_delay)
                        comp.save()
                        message = f"Delay updated for {comp.name}."
                except Competitor.DoesNotExist:
                    message = "Competitor not found."
        elif "add_competitor" in request.POST:
            competitor_form = CompetitorForm(request.POST)
            if competitor_form.is_valid():
                drop = competitor_form.cleaned_data["drop"]
                if drop.status != "pending":
                    message = "Cannot add competitor to captured/missed drops."
                else:
                    name = competitor_form.cleaned_data["name"]
                    attempts = competitor_form.cleaned_data["attempts"]
                    Competitor.objects.create(drop=drop, name=name, attempts=attempts)
                    message = "Competitor added."

    domains = Domain.objects.all().order_by("-created_at")[:20]
    # drops already set above
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
