from django.core.management.base import BaseCommand
from django.utils import timezone
from core.models import Domain, Drop
import socketserver
import threading
import xml.etree.ElementTree as ET

EPP_GREETING = '''<?xml version="1.0" encoding="UTF-8"?>
<epp xmlns="urn:ietf:params:xml:ns:epp-1.0">
  <greeting>
    <svID>Mock Nominet EPP</svID>
    <svDate>{now}</svDate>
    <svcMenu>
      <version>1.0</version>
      <lang>en</lang>
      <objURI>urn:ietf:params:xml:ns:domain-1.0</objURI>
    </svcMenu>
  </greeting>
</epp>'''

EPP_RESPONSE_SUCCESS = '''<?xml version="1.0" encoding="UTF-8"?>
<epp xmlns="urn:ietf:params:xml:ns:epp-1.0">
  <response>
    <result code="1000">
      <msg>Command completed successfully</msg>
    </result>
  </response>
</epp>'''

class EPPHandler(socketserver.BaseRequestHandler):
    def handle(self):
        from core.models import Domain, Drop, Competitor
        import time
        greeting = EPP_GREETING.format(now=timezone.now().isoformat())
        self.send_epp(greeting)
        while True:
            try:
                data = self.receive_epp()
                if not data:
                    break
                root = ET.fromstring(data)
                # Handle <check> command
                if root.find('.//{*}check') is not None:
                    domain_name = self._extract_domain_name(root)
                    if domain_name:
                        exists = Domain.objects.filter(name=domain_name.split('.')[0], tld=domain_name.split('.')[-1]).exists()
                        if exists:
                            response = self._epp_check_response(domain_name, avail=False)
                        else:
                            response = self._epp_check_response(domain_name, avail=True)
                        self.send_epp(response)
                    else:
                        self.send_epp(EPP_RESPONSE_SUCCESS)
                # Handle <create> command
                elif root.find('.//{*}create') is not None:
                    domain_name = self._extract_domain_name(root)
                    if domain_name:
                        name, tld = domain_name.split('.')
                        # Find the drop for this domain
                        try:
                            domain_obj = Domain.objects.get(name=name, tld=tld)
                            drop = Drop.objects.filter(domain=domain_obj).order_by('-drop_time').first()
                        except Domain.DoesNotExist:
                            drop = None
                        # If drop exists and is due, simulate all competitors
                        if drop and drop.drop_time <= timezone.now():
                            competitors = list(drop.competitors.all())
                            # Add the real request as a competitor with delay 0
                            competitors.append(type('RealCompetitor', (), {'name': 'You', 'delay_ms': 0, 'is_real': True})())
                            # Sort by delay
                            competitors.sort(key=lambda c: c.delay_ms)
                            winner = None
                            for comp in competitors:
                                time.sleep(comp.delay_ms / 1000.0)
                                # Check if domain is still available
                                exists = Domain.objects.filter(name=name, tld=tld).exists()
                                if not exists:
                                    Domain.objects.create(name=name, tld=tld)
                                    Drop.objects.create(domain=Domain.objects.get(name=name, tld=tld), drop_time=timezone.now() + timezone.timedelta(days=1))
                                    winner = comp
                                    break
                            if winner and getattr(winner, 'is_real', False):
                                response = self._epp_create_response(domain_name, success=True)
                            else:
                                response = self._epp_create_response(domain_name, success=False)
                            self.send_epp(response)
                        else:
                            # No drop or not due, fallback to normal create
                            domain, created = Domain.objects.get_or_create(name=name, tld=tld)
                            if created:
                                Drop.objects.create(domain=domain, drop_time=timezone.now() + timezone.timedelta(days=1))
                                response = self._epp_create_response(domain_name, success=True)
                            else:
                                response = self._epp_create_response(domain_name, success=False)
                            self.send_epp(response)
                    else:
                        self.send_epp(EPP_RESPONSE_SUCCESS)
                else:
                    self.send_epp(EPP_RESPONSE_SUCCESS)
            except Exception as e:
                # Optionally log the error
                break

    def send_epp(self, xml):
        data = xml.encode('utf-8')
        length = len(data) + 4
        self.request.sendall(length.to_bytes(4, 'big') + data)

    def receive_epp(self):
        # Read 4-byte length prefix
        length_bytes = self.request.recv(4)
        if not length_bytes or len(length_bytes) < 4:
            return None
        length = int.from_bytes(length_bytes, 'big')
        data = b''
        while len(data) < length - 4:
            chunk = self.request.recv(length - 4 - len(data))
            if not chunk:
                break
            data += chunk
        return data.decode('utf-8')

class Command(BaseCommand):
    help = 'Run a mock EPP TCP server (Nominet style) on port 700.'

    def handle(self, *args, **options):
        HOST, PORT = '0.0.0.0', 700
        with socketserver.ThreadingTCPServer((HOST, PORT), EPPHandler) as server:
            self.stdout.write(self.style.SUCCESS(f"Mock EPP server running on {HOST}:{PORT}"))
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                self.stdout.write(self.style.WARNING("Shutting down EPP server."))
