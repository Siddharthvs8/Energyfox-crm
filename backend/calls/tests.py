from django.test import TestCase
from django.utils import timezone
from unittest.mock import patch
from organization.utils import get_org_settings
from users.models import User
from leads.models import Lead, Product
from ai_manager.models import MonthlyTarget, DailyTarget
from calls.models import CallLog

class CallTrackingTestCase(TestCase):
    def setUp(self):
        super().setUp()
        self.org = get_org_settings()
        # Set up a manager/agent user
        self.agent = User.objects.create_user(
            username='testagent',
            email='agent@test.com',
            password='testpassword',
            first_name='Test',
            last_name='Agent'
        )
        
        # Create a product and lead
        self.product = Product.objects.create(name="Test Product", default_price=100)
        self.lead = Lead.objects.create(
            first_name="John",
            last_name="Doe",
            phone="1234567890",
            assigned_to=self.agent,
            product=self.product
        )
        
        # Set monthly target for this month
        now = timezone.now()
        self.monthly_target = MonthlyTarget.objects.create(
            agent=self.agent,
            month=now.month,
            year=now.year,
            target_dialed_calls=10,
            target_call_time=60
        )
        
        # Trigger daily target generation
        from ai_manager.engine import generate_daily_targets
        generate_daily_targets(self.monthly_target)

    def test_call_tracking_updates_daily_target(self):
        now = timezone.now()
        today_date = timezone.localtime(now).date()
        
        # 1. Initially, achievements should be 0
        dt = DailyTarget.objects.get(agent=self.agent, date=today_date)
        self.assertEqual(dt.achieved_dialed_calls, 0)
        self.assertEqual(dt.achieved_call_time, 0)
        
        # 2. Create a connected call log
        call1 = CallLog.objects.create(
            lead=self.lead,
            user=self.agent,
            duration_seconds=125, # 2 mins 5 seconds -> rounds to 2 mins
            outcome='connected'
        )
        
        # Refresh and verify
        dt.refresh_from_db()
        self.assertEqual(dt.achieved_dialed_calls, 1)
        self.assertEqual(dt.achieved_call_time, 2)
        
        # 3. Create a non-connected call log (should not update parameters)
        call2 = CallLog.objects.create(
            lead=self.lead,
            user=self.agent,
            duration_seconds=300,
            outcome='busy'
        )
        
        # Refresh and verify (counts should not change)
        dt.refresh_from_db()
        self.assertEqual(dt.achieved_dialed_calls, 1)
        self.assertEqual(dt.achieved_call_time, 2)
        
        # 4. Update non-connected call log to connected (e.g. status callback updates it)
        call2.outcome = 'connected'
        call2.duration_seconds = 180 # 3 mins
        call2.save()
        
        dt.refresh_from_db()
        self.assertEqual(dt.achieved_dialed_calls, 2)
        self.assertEqual(dt.achieved_call_time, 5) # 2 mins + 3 mins = 5 mins
        
        # 5. Delete a connected call log
        call1.delete()
        
        dt.refresh_from_db()
        self.assertEqual(dt.achieved_dialed_calls, 1)
        self.assertEqual(dt.achieved_call_time, 3) # only call2 is left

    @patch('requests.post')
    def test_exotel_call_initiation(self, mock_post):
        from unittest.mock import MagicMock
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"Call": {"Sid": "exotel_sid_999", "Status": "queued"}}
        mock_post.return_value = mock_response

        # Update org settings to use Exotel
        self.org.telephony_provider = 'exotel'
        self.org.exotel_sid = 'beehub1'
        self.org.exotel_api_key = 'apikey'
        self.org.exotel_api_token = 'apitoken'
        self.org.exotel_callerid = '123456'
        self.org.save()

        # Update agent phone number
        self.agent.phone = '+919900000000'
        self.agent.save()

        # Initiate call
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(self.agent)
        token = str(refresh.access_token)
        response = self.client.post(
            '/api/calls/initiate/',
            {'lead_id': self.lead.id},
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token}'
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('Call initiated successfully', response.json()['status'])
        self.assertEqual(response.json()['sid'], 'exotel_sid_999')

        # Check CallLog was created
        call_log = CallLog.objects.get(exotel_sid='exotel_sid_999')
        self.assertEqual(call_log.outcome, 'initiated')
        self.assertEqual(call_log.user, self.agent)
        self.assertEqual(call_log.lead, self.lead)

    def test_exotel_webhook_callback(self):
        # Create an initiated call log
        call_log = CallLog.objects.create(
            lead=self.lead,
            user=self.agent,
            exotel_sid='exotel_sid_888',
            outcome='initiated'
        )

        # Send status callback to the webhook
        webhook_url = '/api/calls/webhook/exotel/'
        payload = {
            'CallSid': 'exotel_sid_888',
            'Status': 'completed',
            'ConversationDuration': '150',
            'RecordingUrl': 'https://example.com/recording.mp3'
        }
        # Send as JSON (mocking content-type application/json)
        import json
        response = self.client.post(webhook_url, json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 200)

        # Verify call log is updated
        call_log.refresh_from_db()
        self.assertEqual(call_log.outcome, 'connected')
        self.assertEqual(call_log.duration_seconds, 150)
        self.assertEqual(call_log.recording_url, 'https://example.com/recording.mp3')

    @patch('requests.get')
    def test_recording_proxy_authentication(self, mock_get):
        from unittest.mock import MagicMock
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {'Content-Type': 'audio/mpeg', 'Content-Length': '12'}
        mock_response.iter_content.return_value = [b'chunk1', b'chunk2']
        mock_get.return_value = mock_response

        # Create a call log with a recording URL
        call_log = CallLog.objects.create(
            lead=self.lead,
            user=self.agent,
            exotel_sid='exotel_sid_777',
            outcome='connected',
            recording_url='https://recordings.exotel.com/xyz.mp3'
        )

        # 1. Access without authentication -> should return 401
        response = self.client.get(f'/api/calls/{call_log.id}/recording_proxy/')
        self.assertEqual(response.status_code, 401)

        # 2. Access with valid JWT token in query params -> should succeed and stream content
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(self.agent)
        token = str(refresh.access_token)

        response = self.client.get(f'/api/calls/{call_log.id}/recording_proxy/?token={token}')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'audio/mpeg')
        self.assertEqual(response.getvalue(), b'chunk1chunk2')

        # 3. Access with valid JWT token in header -> should succeed and stream content
        response = self.client.get(
            f'/api/calls/{call_log.id}/recording_proxy/',
            HTTP_AUTHORIZATION=f'Bearer {token}'
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.getvalue(), b'chunk1chunk2')

    def test_exotel_inbound_call_creation(self):
        # Configure org virtual number
        self.org.exotel_callerid = '+919988776655'
        self.org.save()

        # Update agent phone number to match agent lookup
        self.agent.phone = '+919900000000'
        self.agent.save()

        # Make sure lead phone matches suffix lookup
        self.lead.phone = '9876543210'
        self.lead.save()

        # Send inbound status callback to the webhook
        webhook_url = '/api/calls/webhook/exotel/'
        payload = {
            'CallSid': 'exotel_sid_inbound_123',
            'Status': 'completed',
            'ConversationDuration': '120', # 2 minutes
            'RecordingUrl': 'https://example.com/inbound.mp3',
            'Direction': 'inbound',
            'From': '9876543210', # Customer
            'To': '+919988776655', # Virtual ExoPhone (To)
            'DialWhomNumber': '+919900000000' # Agent (DialWhomNumber)
        }
        
        import json
        response = self.client.post(webhook_url, json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 200)

        # Check CallLog was created
        call_log = CallLog.objects.get(exotel_sid='exotel_sid_inbound_123')
        self.assertEqual(call_log.direction, 'inbound')
        self.assertEqual(call_log.outcome, 'connected')
        self.assertEqual(call_log.duration_seconds, 120)
        self.assertEqual(call_log.lead, self.lead)
        self.assertEqual(call_log.user, self.agent)

        # Check daily target updated in real-time
        from ai_manager.models import DailyTarget
        dt = DailyTarget.objects.get(agent=self.agent, date=timezone.localtime(call_log.created_at).date())
        self.assertEqual(dt.achieved_dialed_calls, 1)
        self.assertEqual(dt.achieved_call_time, 2)

    def test_voxbay_inbound_call_creation(self):
        # Configure org virtual number
        self.org.voxbay_callerid = '9900112233'
        self.org.save()

        # Update agent voxbay extension
        self.agent.voxbay_extension = '105'
        self.agent.save()

        # Make sure lead phone matches suffix lookup
        self.lead.phone = '8887776665'
        self.lead.save()

        webhook_url = '/api/calls/webhook/voxbay/'
        payload = {
            'calluuid': 'voxbay_uuid_inbound_123',
            'status': 'Answered',
            'duration': '180', # 3 minutes
            'recording_url': 'rec_inbound.wav',
            'callerNumber': '8887776665', # Customer
            'AgentNumber': '105', # Agent extension
            'did': '9900112233' # Virtual number
        }

        import json
        response = self.client.post(webhook_url, json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 200)

        # Check CallLog was created
        call_log = CallLog.objects.get(voxbay_uuid='voxbay_uuid_inbound_123')
        self.assertEqual(call_log.direction, 'inbound')
        self.assertEqual(call_log.outcome, 'connected')
        self.assertEqual(call_log.duration_seconds, 180)
        self.assertEqual(call_log.lead, self.lead)
        self.assertEqual(call_log.user, self.agent)

        # Check daily target updated in real-time
        from ai_manager.models import DailyTarget
        dt = DailyTarget.objects.get(agent=self.agent, date=timezone.localtime(call_log.created_at).date())
        self.assertEqual(dt.achieved_dialed_calls, 1)
        self.assertEqual(dt.achieved_call_time, 3)


