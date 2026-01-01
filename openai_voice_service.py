"""
OpenAI GPT-4o Realtime API integration with Twilio
Provides ultra-low latency voice conversations using WebSocket streaming
"""
import os
import json
import base64
import asyncio
import websockets
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Connect, Stream
from flask import Flask, request, Response
from dotenv import load_dotenv

load_dotenv()

class OpenAIVoiceService:
    """
    Integrates OpenAI Realtime API with Twilio for real-time voice conversations
    """
    def __init__(self):
        self.openai_api_key = os.environ.get('OPENAI_API_KEY')
        self.twilio_account_sid = os.environ.get('TWILIO_ACCOUNT_SID')
        self.twilio_auth_token = os.environ.get('TWILIO_AUTH_TOKEN')
        self.twilio_phone_number = os.environ.get('TWILIO_PHONE_NUMBER')

        if not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY not found in environment")
        if not all([self.twilio_account_sid, self.twilio_auth_token, self.twilio_phone_number]):
            raise ValueError("Twilio credentials not found in environment")

        self.twilio_client = Client(self.twilio_account_sid, self.twilio_auth_token)
        self.active_sessions = {}

    def make_call(self, to_number, webhook_url):
        """
        Initiate a call using Twilio

        Args:
            to_number: Phone number to call (E.164 format)
            webhook_url: URL for Twilio to call for TwiML instructions

        Returns:
            Call SID
        """
        try:
            call = self.twilio_client.calls.create(
                to=to_number,
                from_=self.twilio_phone_number,
                url=webhook_url + '/incoming-call',
                method='POST',
                status_callback=webhook_url + '/call-status',
                status_callback_event=['completed', 'failed']
            )
            print(f"Call initiated! Call SID: {call.sid}")
            return call.sid
        except Exception as e:
            print(f"Error making call: {e}")
            return None


class OpenAICallServer:
    """
    Flask + WebSocket server for handling Twilio Media Streams with OpenAI Realtime API
    """
    def __init__(self, system_instructions, greeting_message=None):
        self.app = Flask(__name__)
        self.system_instructions = system_instructions
        self.greeting_message = greeting_message
        self.openai_api_key = os.environ.get('OPENAI_API_KEY')
        self.setup_routes()

    def setup_routes(self):
        @self.app.route('/incoming-call', methods=['POST'])
        def incoming_call():
            """Handle incoming call from Twilio"""
            call_sid = request.values.get('CallSid')
            print(f"\n[Call {call_sid}] Incoming call received")

            response = VoiceResponse()

            # Start bidirectional media stream to WebSocket
            # Use the same host but explicitly use the WebSocket port
            host = request.host.split(':')[0]  # Remove port if present
            connect = Connect()
            # Twilio will connect to the WebSocket on the same ngrok domain
            stream = Stream(url=f'wss://{host}/media-stream')
            connect.append(stream)
            response.append(connect)

            print(f"[TwiML] Directing Twilio to WebSocket: wss://{host}/media-stream")
            return Response(str(response), mimetype='text/xml')

        @self.app.route('/call-status', methods=['POST'])
        def call_status():
            """Handle call status updates"""
            call_sid = request.values.get('CallSid')
            call_status = request.values.get('CallStatus')
            print(f"[Call {call_sid}] Status: {call_status}")
            return '', 200

        @self.app.route('/health', methods=['GET'])
        def health():
            """Health check endpoint"""
            return {'status': 'healthy'}, 200

    async def handle_media_stream(self, websocket, path):
        """
        Handle bidirectional WebSocket connection between Twilio and OpenAI
        """
        print("\n[WebSocket] New connection established")

        call_sid = None
        stream_sid = None
        openai_ws = None

        try:
            # Connect to OpenAI Realtime API
            openai_ws = await websockets.connect(
                'wss://api.openai.com/v1/realtime?model=gpt-realtime',
                additional_headers={
                    "Authorization": f"Bearer {self.openai_api_key}",
                    "OpenAI-Beta": "realtime=v1"
                }
            )
            print("[OpenAI] Connected to Realtime API")

            # Configure session
            session_config = {
                "type": "session.update",
                "session": {
                    "turn_detection": {"type": "server_vad"},
                    "input_audio_format": "g711_ulaw",
                    "output_audio_format": "g711_ulaw",
                    "voice": "coral",
                    "instructions": self.system_instructions,
                    "modalities": ["text", "audio"],
                    "temperature": 0.8,
                    "input_audio_transcription": {
                        "model": "whisper-1"
                    }
                }
            }
            await openai_ws.send(json.dumps(session_config))
            print("[OpenAI] Session configured")

            # If greeting message is provided, send it immediately
            if self.greeting_message:
                print(f"[OpenAI] Sending greeting: {self.greeting_message}")
                greeting_event = {
                    "type": "response.create",
                    "response": {
                        "modalities": ["text", "audio"],
                        "instructions": f"Say this greeting: {self.greeting_message}"
                    }
                }
                await openai_ws.send(json.dumps(greeting_event))

            # Create tasks for bidirectional streaming
            async def twilio_to_openai():
                """Forward audio from Twilio to OpenAI"""
                nonlocal call_sid, stream_sid
                async for message in websocket:
                    data = json.loads(message)

                    if data['event'] == 'start':
                        call_sid = data['start']['callSid']
                        stream_sid = data['start']['streamSid']
                        print(f"[Twilio] Stream started - Call: {call_sid}, Stream: {stream_sid}")

                    elif data['event'] == 'media':
                        # Forward audio to OpenAI
                        audio_append = {
                            "type": "input_audio_buffer.append",
                            "audio": data['media']['payload']
                        }
                        await openai_ws.send(json.dumps(audio_append))

                    elif data['event'] == 'stop':
                        print(f"[Twilio] Stream stopped")
                        break

            async def openai_to_twilio():
                """Forward audio from OpenAI to Twilio"""
                async for message in openai_ws:
                    response = json.loads(message)

                    if response['type'] == 'response.audio.delta':
                        # Forward audio to Twilio
                        audio_delta = {
                            "event": "media",
                            "streamSid": stream_sid,
                            "media": {
                                "payload": response['delta']
                            }
                        }
                        await websocket.send(json.dumps(audio_delta))

                    elif response['type'] == 'response.audio_transcript.done':
                        transcript = response.get('transcript', '')
                        print(f"[Agent] Said: {transcript}")

                    elif response['type'] == 'conversation.item.input_audio_transcription.completed':
                        transcript = response.get('transcript', '')
                        print(f"[Receptionist] Said: {transcript}")

                    elif response['type'] == 'error':
                        error = response.get('error', {})
                        print(f"[OpenAI] Error: {error}")

            # Run both directions concurrently
            await asyncio.gather(
                twilio_to_openai(),
                openai_to_twilio()
            )

        except Exception as e:
            print(f"[Error] WebSocket error: {e}")
        finally:
            if openai_ws:
                await openai_ws.close()
            print("[WebSocket] Connection closed")

    def run(self, host='0.0.0.0', port=5001):
        """Start the Flask server with integrated WebSocket support"""
        from flask_sock import Sock

        # Add WebSocket support to Flask
        sock = Sock(self.app)

        @sock.route('/media-stream')
        def media_stream_route(ws):
            """Handle WebSocket connections on the same port as HTTP"""
            import asyncio

            # Run the async WebSocket handler
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            # Wrap the flask-sock WebSocket to work with our async handler
            class WebSocketWrapper:
                def __init__(self, ws):
                    self._ws = ws

                def __aiter__(self):
                    return self

                async def __anext__(self):
                    try:
                        # Run synchronous receive in executor to make it async-compatible
                        loop = asyncio.get_event_loop()
                        data = await loop.run_in_executor(None, self._ws.receive)
                        if data is None:
                            raise StopAsyncIteration
                        return data
                    except:
                        raise StopAsyncIteration

                async def send(self, data):
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(None, self._ws.send, data)

                async def close(self):
                    pass

            wrapped_ws = WebSocketWrapper(ws)
            loop.run_until_complete(self.handle_media_stream(wrapped_ws, '/media-stream'))

        # Start Flask HTTP server with WebSocket support
        print(f"[HTTP + WebSocket] Server running on http://{host}:{port}")
        print(f"[WebSocket] Endpoint: ws://{host}:{port}/media-stream")
        self.app.run(host=host, port=port, debug=False)

