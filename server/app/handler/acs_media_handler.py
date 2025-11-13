"""Handles media streaming to Azure Voice Live API via WebSocket."""

import asyncio
import base64
import json
import logging
import uuid

from azure.identity.aio import ManagedIdentityCredential
from websockets.asyncio.client import connect as ws_connect
from websockets.typing import Data

logger = logging.getLogger(__name__)


def session_config():
    """Returns the default session configuration for Voice Live.
    Note: When using Azure AI Foundry agents, agent parameters are passed as query parameters
    in the WebSocket URL, not in the session configuration.
    """
    return {
        "type": "session.update",
        "session": {
            "turn_detection": {
                "type": "azure_semantic_vad",
                "threshold": 0.3,
                "prefix_padding_ms": 200,
                "silence_duration_ms": 200,
                "remove_filler_words": False,
                "end_of_utterance_detection": {
                    "model": "semantic_detection_v1",
                    "threshold": 0.01,
                    "timeout": 2,
                },
            },
            "input_audio_noise_reduction": {"type": "azure_deep_noise_suppression"},
            "input_audio_echo_cancellation": {"type": "server_echo_cancellation"},
            "voice": {
                "name": "en-US-AvaMultilingualNeural",
                "type": "azure-standard",
                "temperature": 0.8,
            },
        },
    }


class ACSMediaHandler:
    """Manages audio streaming between client and Azure Voice Live API."""

    def __init__(self, config):
        self.endpoint = config["AZURE_VOICE_LIVE_ENDPOINT"]
        self.model = config["VOICE_LIVE_MODEL"]
        self.api_key = config["AZURE_VOICE_LIVE_API_KEY"]
        self.client_id = config["AZURE_USER_ASSIGNED_IDENTITY_CLIENT_ID"]
        self.agent_id = config.get("AZURE_AI_AGENT_ID")
        self.project_name = config.get("AZURE_AI_PROJECT_NAME")
        self.send_queue = asyncio.Queue()
        self.ws = None
        self.send_task = None
        self.incoming_websocket = None
        self.is_raw_audio = True
        self.session_ready = False
        self.greeting_sent = False  # Track if proactive greeting has been sent

    def _generate_guid(self):
        return str(uuid.uuid4())

    async def connect(self):
        """Connects to Azure Voice Live API via WebSocket."""
        from urllib.parse import urlencode
        
        endpoint = self.endpoint.rstrip("/")
        
        # Build query parameters
        query_params = {"api-version": "2025-10-01"}
        
        # If agent_id is provided, use agent-based connection
        if self.agent_id and self.project_name:
            logger.info(f"[VoiceLiveACSHandler] Connecting with Azure AI Foundry Agent: {self.agent_id}")
            query_params["agent-id"] = self.agent_id
            query_params["agent-project-name"] = self.project_name
            
            # Get agent access token
            if self.client_id:
                async with ManagedIdentityCredential(client_id=self.client_id) as credential:
                    agent_token = await credential.get_token(
                        "https://ai.azure.com/.default"
                    )
                    query_params["agent-access-token"] = agent_token.token
                    logger.info("[VoiceLiveACSHandler] Obtained agent access token with managed identity")
            else:
                from azure.identity.aio import DefaultAzureCredential
                async with DefaultAzureCredential() as credential:
                    agent_token = await credential.get_token(
                        "https://ai.azure.com/.default"
                    )
                    query_params["agent-access-token"] = agent_token.token
                    logger.info("[VoiceLiveACSHandler] Obtained agent access token with default credential")
        else:
            # Standard model-based connection
            model = self.model.strip()
            query_params["model"] = model
            logger.info(f"[VoiceLiveACSHandler] Connecting with model: {model}")
        
        # Build WebSocket URL
        query_string = urlencode(query_params)
        url = f"{endpoint}/voice-live/realtime?{query_string}"
        url = url.replace("https://", "wss://").replace("http://", "ws://")
        
        logger.info(f"[VoiceLiveACSHandler] WebSocket URL: {url[:100]}...")  # Log first 100 chars for security
        logger.info(f"[VoiceLiveACSHandler] Query params: {list(query_params.keys())}")

        headers = {"x-ms-client-request-id": self._generate_guid()}

        # Add authentication header
        # Agent mode requires Bearer token authentication (not API key)
        # Standard model mode can use API key or Bearer token
        if self.agent_id and self.project_name:
            # Agent mode: MUST use Bearer token with Cognitive Services scope
            if self.client_id:
                async with ManagedIdentityCredential(client_id=self.client_id) as credential:
                    token = await credential.get_token(
                        "https://cognitiveservices.azure.com/.default"
                    )
                    headers["Authorization"] = f"Bearer {token.token}"
                    logger.info("[VoiceLiveACSHandler] Authenticated with managed identity for agent")
            else:
                from azure.identity.aio import DefaultAzureCredential
                async with DefaultAzureCredential() as credential:
                    token = await credential.get_token(
                        "https://cognitiveservices.azure.com/.default"
                    )
                    headers["Authorization"] = f"Bearer {token.token}"
                    logger.info("[VoiceLiveACSHandler] Authenticated with Bearer token for agent")
        else:
            # Standard model mode: can use API key
            if self.client_id:
                async with ManagedIdentityCredential(client_id=self.client_id) as credential:
                    token = await credential.get_token(
                        "https://cognitiveservices.azure.com/.default"
                    )
                    headers["Authorization"] = f"Bearer {token.token}"
                    logger.info("[VoiceLiveACSHandler] Authenticated with managed identity")
            else:
                headers["api-key"] = self.api_key
                logger.info("[VoiceLiveACSHandler] Authenticated with API key")

        try:
            self.ws = await ws_connect(url, additional_headers=headers)
            logger.info("[VoiceLiveACSHandler] Connected to Voice Live API")
        except Exception as e:
            logger.error(f"[VoiceLiveACSHandler] Failed to connect to Voice Live API: {type(e).__name__}: {e}")
            raise

        # Start receiver and sender loops BEFORE sending any messages
        asyncio.create_task(self._receiver_loop())
        self.send_task = asyncio.create_task(self._sender_loop())

        # IMPORTANT: Even for agents, we must send session.update with voice and audio settings
        # The agent provides instructions/prompts, but session config controls voice, VAD, etc.
        await self._send_json(session_config())
        logger.info("[VoiceLiveACSHandler] Session config sent (voice and audio settings)")

    async def init_incoming_websocket(self, socket, is_raw_audio=True):
        """Sets up incoming ACS WebSocket."""
        self.incoming_websocket = socket
        self.is_raw_audio = is_raw_audio

    async def audio_to_voicelive(self, audio_b64: str):
        """Queues audio data to be sent to Voice Live API."""
        await self.send_queue.put(
            json.dumps({"type": "input_audio_buffer.append", "audio": audio_b64})
        )

    async def _send_json(self, obj):
        """Sends a JSON object over WebSocket."""
        if self.ws:
            await self.ws.send(json.dumps(obj))

    async def _sender_loop(self):
        """Continuously sends messages from the queue to the Voice Live WebSocket."""
        try:
            while True:
                msg = await self.send_queue.get()
                if self.ws:
                    await self.ws.send(msg)
        except Exception:
            logger.exception("[VoiceLiveACSHandler] Sender loop error")

    async def _receiver_loop(self):
        """Handles incoming events from the Voice Live WebSocket."""
        try:
            async for message in self.ws:
                event = json.loads(message)
                event_type = event.get("type")

                match event_type:
                    case "session.created":
                        session_id = event.get("session", {}).get("id")
                        logger.info("[VoiceLiveACSHandler] Session ID: %s", session_id)
                        
                    case "session.updated":
                        logger.info("[VoiceLiveACSHandler] Session updated successfully")
                        self.session_ready = True
                        
                        # Send proactive greeting for agent mode after session is updated
                        if self.agent_id and self.project_name and not self.greeting_sent:
                            self.greeting_sent = True
                            await self._send_json({"type": "response.create"})
                            logger.info("[VoiceLiveACSHandler] Sent response.create for proactive greeting")

                    case "input_audio_buffer.cleared":
                        logger.info("Input Audio Buffer Cleared Message")

                    case "input_audio_buffer.speech_started":
                        logger.info(
                            "Voice activity detection started at %s ms",
                            event.get("audio_start_ms"),
                        )
                        await self.stop_audio()

                    case "input_audio_buffer.speech_stopped":
                        logger.info("Speech stopped")

                    case "conversation.item.input_audio_transcription.completed":
                        transcript = event.get("transcript")
                        logger.info("User: %s", transcript)
                        await self.send_message(
                            json.dumps({"Kind": "Transcription", "Text": transcript, "Speaker": "User"})
                        )

                    case "conversation.item.input_audio_transcription.failed":
                        error_msg = event.get("error")
                        logger.warning("Transcription Error: %s", error_msg)

                    case "response.done":
                        response = event.get("response", {})
                        logger.info("Response Done: Id=%s", response.get("id"))
                        if response.get("status_details"):
                            logger.info(
                                "Status Details: %s",
                                json.dumps(response["status_details"], indent=2),
                            )

                    case "response.audio_transcript.done":
                        transcript = event.get("transcript")
                        logger.info("AI: %s", transcript)
                        await self.send_message(
                            json.dumps({"Kind": "Transcription", "Text": transcript, "Speaker": "Assistant"})
                        )

                    case "response.audio.delta":
                        delta = event.get("delta")
                        if self.is_raw_audio:
                            audio_bytes = base64.b64decode(delta)
                            await self.send_message(audio_bytes)
                        else:
                            await self.voicelive_to_acs(delta)

                    case "error":
                        logger.error("Voice Live Error: %s", event)

                    case _:
                        logger.debug(
                            "[VoiceLiveACSHandler] Other event: %s", event_type
                        )
        except Exception:
            logger.exception("[VoiceLiveACSHandler] Receiver loop error")

    async def send_message(self, message: Data):
        """Sends data back to client WebSocket."""
        try:
            await self.incoming_websocket.send(message)
        except Exception:
            logger.exception("[VoiceLiveACSHandler] Failed to send message")

    async def voicelive_to_acs(self, base64_data):
        """Converts Voice Live audio delta to ACS audio message."""
        try:
            data = {
                "Kind": "AudioData",
                "AudioData": {"Data": base64_data},
                "StopAudio": None,
            }
            await self.send_message(json.dumps(data))
        except Exception:
            logger.exception("[VoiceLiveACSHandler] Error in voicelive_to_acs")

    async def stop_audio(self):
        """Sends a StopAudio signal to ACS."""
        stop_audio_data = {"Kind": "StopAudio", "AudioData": None, "StopAudio": {}}
        await self.send_message(json.dumps(stop_audio_data))

    async def acs_to_voicelive(self, stream_data):
        """Processes audio from ACS and forwards to Voice Live if not silent."""
        try:
            data = json.loads(stream_data)
            if data.get("kind") == "AudioData":
                audio_data = data.get("audioData", {})
                if not audio_data.get("silent", True):
                    await self.audio_to_voicelive(audio_data.get("data"))
        except Exception:
            logger.exception("[VoiceLiveACSHandler] Error processing ACS audio")

    async def web_to_voicelive(self, audio_bytes):
        """Encodes raw audio bytes and sends to Voice Live API."""
        audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
        await self.audio_to_voicelive(audio_b64)
