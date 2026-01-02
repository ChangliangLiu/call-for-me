"""
Azure Voice Live API integration with Twilio
Provides ultra-low latency voice conversations using Azure's realtime voice API
"""
import os
import json
import base64
import asyncio
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Connect, Stream
from flask import Flask, request, Response
from dotenv import load_dotenv
from typing import Union, Optional
from azure.core.credentials import AzureKeyCredential
from azure.ai.voicelive.aio import connect
from azure.ai.voicelive.models import (
    AudioEchoCancellation,
    AudioNoiseReduction,
    AzureStandardVoice,
    InputAudioFormat,
    Modality,
    OutputAudioFormat,
    RequestSession,
    ServerEventType,
    ServerVad,
    AzureSemanticVadEn,
)
from call_audio_logger import CallAudioLogger

load_dotenv()


class AzureVoiceService:
    """
    Integrates Azure Voice Live API with Twilio for real-time voice conversations
    """
    def __init__(self):
        self.azure_api_key = os.environ.get('AZURE_VOICELIVE_API_KEY')
        self.azure_endpoint = os.environ.get('AZURE_VOICELIVE_ENDPOINT')
        self.azure_model = os.environ.get('AZURE_VOICELIVE_MODEL')
        self.twilio_account_sid = os.environ.get('TWILIO_ACCOUNT_SID')
        self.twilio_auth_token = os.environ.get('TWILIO_AUTH_TOKEN')
        self.twilio_phone_number = os.environ.get('TWILIO_PHONE_NUMBER')

        if not self.azure_api_key:
            raise ValueError("AZURE_VOICELIVE_API_KEY not found in environment")
        if not self.azure_endpoint:
            raise ValueError("AZURE_VOICELIVE_ENDPOINT not found in environment")
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


class AzureCallServer:
    """
    Flask + WebSocket server for handling Twilio Media Streams with Azure Voice Live API
    """
    def __init__(self, system_instructions, greeting_message=None):
        self.app = Flask(__name__)
        self.system_instructions = system_instructions
        self.greeting_message = greeting_message
        self.azure_api_key = os.environ.get('AZURE_VOICELIVE_API_KEY')
        self.azure_endpoint = os.environ.get('AZURE_VOICELIVE_ENDPOINT')
        self.azure_model = os.environ.get('AZURE_VOICELIVE_MODEL')
        self.voice_name = os.environ.get('AZURE_VOICELIVE_VOICE')
        self.setup_routes()

    def setup_routes(self):
        @self.app.route('/incoming-call', methods=['POST'])
        def incoming_call():
            """Handle incoming call from Twilio"""
            call_sid = request.values.get('CallSid')
            print(f"\n[Call {call_sid}] Incoming call received")

            response = VoiceResponse()

            # Start bidirectional media stream to WebSocket
            host = request.host.split(':')[0]  # Remove port if present
            connect = Connect()
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
        Handle bidirectional WebSocket connection between Twilio and Azure Voice Live
        """
        print("\n[WebSocket] New connection established")

        call_sid = None
        stream_sid = None
        azure_connection = None
        audio_logger = None

        try:
            # Connect to Azure Voice Live API
            credential = AzureKeyCredential(self.azure_api_key)

            async with connect(
                endpoint=self.azure_endpoint,
                credential=credential,
                model=self.azure_model
            ) as conn:
                azure_connection = conn
                print("[Azure] Connected to Voice Live API")

                # Configure session for voice conversation
                await self._configure_session(conn)
                print("[Azure] Session configured")

                # Create tasks for bidirectional streaming
                async def twilio_to_azure():
                    """Forward audio from Twilio to Azure"""
                    nonlocal call_sid, stream_sid, audio_logger
                    try:
                        async for message in websocket:
                            data = json.loads(message)

                            if data['event'] == 'start':
                                call_sid = data['start']['callSid']
                                stream_sid = data['start']['streamSid']
                                print(f"[Twilio] Stream started - Call: {call_sid}, Stream: {stream_sid}")
                                
                                # Initialize audio logger for this call
                                audio_logger = CallAudioLogger(call_sid)
                                print(f"[AudioLogger] Started logging for call {call_sid}")
                                
                                # If greeting message is provided, send it immediately after stream starts
                                if self.greeting_message:
                                    print(f"[Azure] Sending greeting: {self.greeting_message}")
                                    try:
                                        # The greeting is already in system_instructions with a directive to speak it immediately
                                        # We just need to trigger a response to make Azure speak proactively
                                        # Try to temporarily disable turn detection to allow proactive speaking
                                        await conn.session.update(
                                            session=RequestSession(
                                                turn_detection=None  # Temporarily disable VAD
                                            )
                                        )
                                        # Small delay to ensure session update is processed
                                        await asyncio.sleep(0.1)
                                        # Trigger response - this should cause Azure to speak the greeting
                                        await conn.response.create()
                                        # Re-enable turn detection
                                        await self._configure_session(conn)
                                        print("[Azure] Greeting response triggered")
                                    except Exception as e:
                                        print(f"[Azure] Warning: Could not send proactive greeting: {e}")
                                        # Fallback: try to trigger response without disabling turn detection
                                        try:
                                            await conn.response.create()
                                            print("[Azure] Attempted to trigger response (greeting in instructions)")
                                        except Exception as e2:
                                            print(f"[Azure] Fallback failed: {e2}")
                                            print("[Azure] Greeting will be sent after caller speaks")

                            elif data['event'] == 'media':
                                # Forward audio to Azure (audio is already base64 encoded from Twilio)
                                audio_payload = data['media']['payload']
                                await conn.input_audio_buffer.append(audio=audio_payload)
                                
                                # Log input audio
                                if audio_logger:
                                    audio_logger.log_input_audio(audio_payload)

                            elif data['event'] == 'stop':
                                print(f"[Twilio] Stream stopped")
                                break
                    except StopAsyncIteration:
                        print("[Twilio] WebSocket connection closed")
                    except Exception as e:
                        print(f"[Error] Error in twilio_to_azure: {e}")
                        raise

                async def azure_to_twilio():
                    """Forward audio and events from Azure to Twilio"""
                    nonlocal audio_logger
                    try:
                        async for event in conn:
                            await self._handle_azure_event(event, websocket, stream_sid, audio_logger)
                    except asyncio.CancelledError:
                        print("[Azure] azure_to_twilio task cancelled")
                        raise
                    except Exception as e:
                        print(f"[Error] Error in azure_to_twilio: {e}")
                        raise

                # Create tasks so we can cancel them
                twilio_task = asyncio.create_task(twilio_to_azure())
                azure_task = asyncio.create_task(azure_to_twilio())

                # Wait for either task to complete, then cancel the other
                done, pending = await asyncio.wait(
                    [twilio_task, azure_task],
                    return_when=asyncio.FIRST_COMPLETED
                )

                # Cancel the pending task
                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                    except Exception as e:
                        print(f"[Warning] Exception while cancelling task: {e}")

                # Check for exceptions in completed tasks
                for task in done:
                    if task.exception():
                        raise task.exception()
                
                # The async with context manager will automatically close the Azure connection
                # when we exit this block. The connection cleanup happens in __aexit__
                print("[Azure] Connection will be closed by context manager")

        except Exception as e:
            print(f"[Error] WebSocket error: {e}")
        finally:
            # Save audio log when call ends
            if audio_logger:
                print("[AudioLogger] Saving call log...")
                audio_logger.save()
            print("[WebSocket] Connection closed")

    async def _configure_session(self, conn):
        """Configure the Azure Voice Live session for phone audio"""
        # Create voice configuration
        voice_config: Union[AzureStandardVoice, str]
        if self.voice_name.startswith("en-US-") or self.voice_name.startswith("en-CA-") or ":" in self.voice_name:
            # Azure voice
            voice_config = AzureStandardVoice(name=self.voice_name)
        else:
            # OpenAI-style voice (alloy, echo, fable, onyx, nova, shimmer, coral)
            voice_config = self.voice_name

        turn_detection_config = AzureSemanticVadEn(
            threshold=0.5,
            prefix_padding_ms=200,
            silence_duration_ms=350,
        )

        # Create session configuration
        # Note: Twilio uses 8kHz μ-law, we'll need to handle conversion
        session_config = RequestSession(
            modalities=[Modality.TEXT, Modality.AUDIO],
            instructions=self.system_instructions,
            voice=voice_config,
            input_audio_format=InputAudioFormat.G711_ULAW,  # Twilio format
            output_audio_format=OutputAudioFormat.G711_ULAW,  # Twilio format
            turn_detection=turn_detection_config,
            input_audio_transcription={"model": "azure-speech", "language": "en-US"},  # Enable receptionist transcription, English only
        )

        await conn.session.update(session=session_config)

    async def _handle_azure_event(self, event, websocket, stream_sid, audio_logger=None):
        """Handle events from Azure Voice Live"""
        if event.type == ServerEventType.SESSION_UPDATED:
            print(f"[Azure] Session ready: {event.session.id}")

        elif event.type == ServerEventType.INPUT_AUDIO_BUFFER_SPEECH_STARTED:
            print("[User] Started speaking")

        elif event.type == ServerEventType.INPUT_AUDIO_BUFFER_SPEECH_STOPPED:
            print("[User] Stopped speaking")

        elif event.type == ServerEventType.RESPONSE_CREATED:
            print("[Agent] Response created")
            # Start a new output audio session
            if audio_logger:
                audio_logger.start_output_session()

        elif event.type == ServerEventType.RESPONSE_AUDIO_DELTA:
            # Forward audio delta to Twilio
            # Azure returns bytes, need to convert to base64 string
            payload = base64.b64encode(event.delta).decode('utf-8')
            # Log output audio chunk (will start session if needed)
            if audio_logger:
                audio_logger.log_output_audio_chunk(event.delta)

            audio_delta = {
                "event": "media",
                "streamSid": stream_sid,
                "media": {
                    "payload": payload
                }
            }
            await websocket.send(json.dumps(audio_delta))

        elif event.type == ServerEventType.RESPONSE_AUDIO_TRANSCRIPT_DONE:
            # Azure provides transcript of agent's speech
            print(f"[Agent] Said: {event.transcript}")
            if audio_logger:
                audio_logger.log_transcript("agent", event.transcript)

        elif event.type == ServerEventType.CONVERSATION_ITEM_INPUT_AUDIO_TRANSCRIPTION_COMPLETED:
            # Azure provides transcript of user's speech
            print(f"[User] Said: {event.transcript}")
            if audio_logger:
                audio_logger.log_transcript("user", event.transcript)

        elif event.type == ServerEventType.RESPONSE_AUDIO_DONE:
            print("[Agent] Finished speaking")
            # End the current output audio session
            if audio_logger:
                audio_logger.end_output_session()

        elif event.type == ServerEventType.RESPONSE_DONE:
            print("[Azure] Response complete")

        elif event.type == ServerEventType.ERROR:
            error = event.error
            print(f"[Azure] Error: {error}")

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
