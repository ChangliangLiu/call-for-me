"""
Audio logger for phone calls
Logs audio from phone calls to WAV files with separate channels for input/output
and saves transcripts to JSON metadata files
"""
import os
import json
import base64
import wave
import audioop
import struct
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Tuple


class CallAudioLogger:
    """
    Logs audio from phone calls to WAV files with separate channels for input/output
    and saves transcripts to JSON metadata files
    
    Input audio (Twilio -> Service): Continuous stream, just concatenate chunks
    Output audio (Service -> Twilio): Can be session-based (Azure) or continuous (OpenAI)
    """
    def __init__(self, call_sid: str, logs_dir: str = "call_logs"):
        self.call_sid = call_sid
        self.logs_dir = Path(logs_dir)
        self.logs_dir.mkdir(exist_ok=True)
        
        # Input audio: continuous stream, just concatenate chunks
        self.input_audio_data: List[int] = []  # List of 16-bit PCM samples (shorts)
        self.first_input_time: Optional[float] = None  # When first input audio chunk arrived
        
        # Output audio: session-based or continuous
        # Each session: (start_timestamp, list_of_pcm_samples)
        self.output_sessions: List[Tuple[float, List[int]]] = []
        self.current_output_session: Optional[Tuple[float, List[int]]] = None  # (start_time, list_of_samples)
        self.use_sessions: bool = True  # True for Azure (session-based), False for OpenAI (continuous)
        
        # Transcript tracking
        self.transcripts: List[dict] = []
        
        # Call metadata
        self.start_time = time.time()
        self.call_metadata = {
            "call_sid": call_sid,
            "start_time": datetime.now().isoformat(),
            "transcripts": []
        }
        
        # Audio format constants (G.711 μ-law: 8kHz, 8-bit, mono)
        self.sample_rate = 8000
        self.sample_width = 2  # 16-bit PCM after conversion
        self.channels = 2  # Stereo: input (left), output (right)
    
    def set_continuous_mode(self, continuous: bool = True):
        """
        Set whether output audio is continuous (OpenAI) or session-based (Azure)
        """
        self.use_sessions = not continuous
    
    def log_input_audio(self, audio_data: str):
        """
        Log input audio chunk from Twilio (continuous stream)
        audio_data: base64-encoded G.711 μ-law audio
        """
        try:
            # Track when first input audio arrives (this becomes time 0)
            if self.first_input_time is None:
                self.first_input_time = time.time() - self.start_time
                print(f"[AudioLogger] First input audio at {self.first_input_time:.3f}s (this becomes time 0)")
            
            # Decode base64
            ulaw_bytes = base64.b64decode(audio_data)
            
            # Convert G.711 μ-law to 16-bit PCM bytes
            pcm_bytes = audioop.ulaw2lin(ulaw_bytes, self.sample_width)
            
            # Convert bytes to list of shorts (16-bit signed integers)
            num_samples = len(pcm_bytes) // self.sample_width
            pcm_samples = list(struct.unpack(f'<{num_samples}h', pcm_bytes))
            
            # Simply concatenate to continuous stream
            self.input_audio_data.extend(pcm_samples)
        except Exception as e:
            print(f"[AudioLogger] Error logging input audio: {e}")
    
    def start_output_session(self):
        """
        Start a new output audio session (called when RESPONSE_CREATED or first RESPONSE_AUDIO_DELTA for Azure)
        """
        if self.current_output_session is None:
            session_start_time = time.time() - self.start_time
            self.current_output_session = (session_start_time, [])
            print(f"[AudioLogger] Started output session at {session_start_time:.3f}s")
    
    def log_output_audio_chunk(self, audio_data: bytes):
        """
        Log output audio chunk from service (within a session for Azure, continuous for OpenAI)
        audio_data: G.711 μ-law bytes
        """
        # Validate input
        if not audio_data or len(audio_data) == 0:
            print("[AudioLogger] Warning: Empty audio chunk received")
            return
        
        # For session-based mode (Azure), start session if not already started
        if self.use_sessions:
            if self.current_output_session is None:
                self.start_output_session()
        
        # Convert G.711 μ-law to 16-bit PCM bytes
        pcm_bytes = audioop.ulaw2lin(audio_data, self.sample_width)
        
        # Convert bytes to list of shorts (16-bit signed integers)
        num_samples = len(pcm_bytes) // self.sample_width
        pcm_samples = list(struct.unpack(f'<{num_samples}h', pcm_bytes))
        
        if self.use_sessions:
            # Concatenate to current session (no gaps)
            _, session_data = self.current_output_session
            session_data.extend(pcm_samples)
        else:
            # For continuous mode (OpenAI), treat as a single continuous session
            if self.current_output_session is None:
                # Start a continuous session when first chunk arrives
                session_start_time = time.time() - self.start_time
                self.current_output_session = (session_start_time, [])
            _, session_data = self.current_output_session
            session_data.extend(pcm_samples)
    
    def end_output_session(self):
        """
        End the current output audio session (called when RESPONSE_AUDIO_DONE for Azure)
        For OpenAI, this can be called when the stream ends
        """
        if self.current_output_session is not None:
            self.output_sessions.append(self.current_output_session)
            start_time, session_data = self.current_output_session
            num_samples = len(session_data)
            duration = num_samples / self.sample_rate
            session_index = len(self.output_sessions) - 1
            print(f"[AudioLogger] Ended output session {session_index} at {start_time:.3f}s, duration {duration:.3f}s, samples: {num_samples}")
            
            self.current_output_session = None
    
    def log_transcript(self, speaker: str, text: str, timestamp: float = None):
        """
        Log a transcript entry
        speaker: 'user' or 'agent'
        text: transcript text
        timestamp: optional timestamp (defaults to current time)
        """
        if timestamp is None:
            timestamp = time.time() - self.start_time
        
        transcript_entry = {
            "speaker": speaker,
            "text": text,
            "timestamp": timestamp,
            "time_iso": datetime.now().isoformat()
        }
        self.transcripts.append(transcript_entry)
        self.call_metadata["transcripts"].append(transcript_entry)
    
    def save(self):
        """
        Save audio to WAV file and transcripts to JSON metadata file
        """
        try:
            # End any active session
            if self.current_output_session is not None:
                self.end_output_session()
            
            # Update metadata
            self.call_metadata["end_time"] = datetime.now().isoformat()
            self.call_metadata["duration_seconds"] = time.time() - self.start_time
            
            # Generate filenames
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            wav_filename = self.logs_dir / f"{self.call_sid}_{timestamp_str}.wav"
            json_filename = self.logs_dir / f"{self.call_sid}_{timestamp_str}_meta.json"
            
            # Save WAV file
            self._save_wav_file(wav_filename)
            
            # Save metadata JSON
            with open(json_filename, 'w') as f:
                json.dump(self.call_metadata, f, indent=2)
            
            print(f"[AudioLogger] Saved call log:")
            print(f"  Audio: {wav_filename}")
            print(f"  Metadata: {json_filename}")
            
        except Exception as e:
            print(f"[AudioLogger] Error saving call log: {e}")
            import traceback
            traceback.print_exc()
    
    def _save_wav_file(self, filename: Path):
        """
        Create a stereo WAV file with input on left channel and output on right channel
        Input: continuous stream (just concatenate)
        Output: session-based (align sessions by start time) or continuous
        """
        if not self.input_audio_data and not self.output_sessions:
            print("[AudioLogger] No audio to save")
            return
        
        # Calculate total duration needed
        # Input duration (number of samples / sample rate)
        input_duration = len(self.input_audio_data) / self.sample_rate
        
        # Calculate output duration (adjust for input offset)
        input_offset = self.first_input_time if self.first_input_time is not None else 0.0
        max_output_time = 0
        for session_start, session_data in self.output_sessions:
            session_duration = len(session_data) / self.sample_rate
            # Adjust session end time relative to input start
            adjusted_end = (session_start - input_offset) + session_duration
            max_output_time = max(max_output_time, adjusted_end)
        
        # Total duration is the maximum of input and output
        total_duration = max(input_duration, max_output_time)
        total_duration += 0.1  # Small padding
        
        # Calculate total samples needed
        total_samples = int(total_duration * self.sample_rate)
        
        # Create buffers for left (input) and right (output) channels
        # Initialize with silence (zeros as shorts)
        left_channel_samples = [0] * total_samples
        right_channel_samples = [0] * total_samples
        
        # Fill input audio (left channel) - continuous stream, start from beginning (time 0)
        input_len = len(self.input_audio_data)
        copy_len = min(input_len, total_samples)
        left_channel_samples[:copy_len] = self.input_audio_data[:copy_len]
        
        # Fill output audio (right channel) - session-based, align by session start time
        # Adjust output session times to be relative to when input audio started
        for session_index, (session_start, session_data) in enumerate(self.output_sessions):
            # Adjust session start time to be relative to when input audio started
            adjusted_start = session_start - input_offset
            sample_offset = int(adjusted_start * self.sample_rate)
            session_len = len(session_data)
            end_offset = min(sample_offset + session_len, total_samples)
            # Only place if offset is non-negative (session happened after input started)
            if sample_offset >= 0 and sample_offset < total_samples:
                copy_len = min(session_len, end_offset - sample_offset)
                right_channel_samples[sample_offset:end_offset] = session_data[:copy_len]
                print(f"[AudioLogger] Placed session {session_index} at offset {sample_offset} (adjusted start {adjusted_start:.3f}s), {copy_len} samples")
            else:
                print(f"[AudioLogger] Warning: Output session {session_index} at {session_start:.3f}s (adjusted {adjusted_start:.3f}s) is outside bounds")
        
        # Convert lists of shorts to bytes and interleave for stereo WAV
        # Pack samples as little-endian 16-bit signed integers
        stereo_samples = []
        for i in range(total_samples):
            stereo_samples.append(left_channel_samples[i])   # Left channel
            stereo_samples.append(right_channel_samples[i])  # Right channel
        
        # Convert list of shorts to bytes (little-endian)
        stereo_bytes = struct.pack(f'<{len(stereo_samples)}h', *stereo_samples)
        
        # Write WAV file
        with wave.open(str(filename), 'wb') as wav_file:
            wav_file.setnchannels(self.channels)
            wav_file.setsampwidth(self.sample_width)
            wav_file.setframerate(self.sample_rate)
            wav_file.writeframes(stereo_bytes)

