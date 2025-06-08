import struct
import logging

logger = logging.getLogger(__name__)

def pcm_to_wav(pcm_data: bytes, sample_rate: int = 24000, channels: int = 1, bits_per_sample: int = 16) -> bytes:
    """
    Convert raw PCM audio data to WAV format that browsers can decode.
    
    Args:
        pcm_data: Raw PCM audio data (16-bit signed, little-endian)
        sample_rate: Sample rate in Hz (Gemini Live API uses 24000)
        channels: Number of audio channels (1 for mono)
        bits_per_sample: Bits per sample (16 for 16-bit audio)
    
    Returns:
        WAV file data as bytes
    """
    try:
        # Calculate format parameters
        byte_rate = sample_rate * channels * bits_per_sample // 8
        block_align = channels * bits_per_sample // 8
        data_size = len(pcm_data)
        
        # WAV file structure:
        # 1. RIFF header (12 bytes)
        # 2. fmt chunk (24 bytes) 
        # 3. data chunk header (8 bytes)
        # 4. PCM data
        
        wav_header = bytearray()
        
        # RIFF header
        wav_header.extend(b'RIFF')                              # ChunkID (4 bytes)
        wav_header.extend(struct.pack('<I', 36 + data_size))    # ChunkSize (4 bytes)
        wav_header.extend(b'WAVE')                              # Format (4 bytes)
        
        # fmt subchunk
        wav_header.extend(b'fmt ')                              # Subchunk1ID (4 bytes)
        wav_header.extend(struct.pack('<I', 16))                # Subchunk1Size (4 bytes)
        wav_header.extend(struct.pack('<H', 1))                 # AudioFormat (2 bytes) - 1 for PCM
        wav_header.extend(struct.pack('<H', channels))          # NumChannels (2 bytes)
        wav_header.extend(struct.pack('<I', sample_rate))       # SampleRate (4 bytes)
        wav_header.extend(struct.pack('<I', byte_rate))         # ByteRate (4 bytes)
        wav_header.extend(struct.pack('<H', block_align))       # BlockAlign (2 bytes)
        wav_header.extend(struct.pack('<H', bits_per_sample))   # BitsPerSample (2 bytes)
        
        # data subchunk
        wav_header.extend(b'data')                              # Subchunk2ID (4 bytes)
        wav_header.extend(struct.pack('<I', data_size))         # Subchunk2Size (4 bytes)
        
        # Combine header with PCM data
        wav_data = bytes(wav_header) + pcm_data
        
        logger.debug(f"Converted PCM to WAV: {len(pcm_data)} bytes → {len(wav_data)} bytes "
                    f"({sample_rate}Hz, {channels}ch, {bits_per_sample}bit)")
        
        return wav_data
        
    except Exception as e:
        logger.error(f"Error converting PCM to WAV: {e}")
        raise

def validate_wav_format(wav_data: bytes) -> bool:
    """
    Validate if the data is a proper WAV file.
    
    Args:
        wav_data: WAV file data to validate
        
    Returns:
        True if valid WAV format, False otherwise
    """
    try:
        if len(wav_data) < 44:  # Minimum WAV header size
            return False
            
        # Check RIFF header
        if wav_data[:4] != b'RIFF':
            return False
            
        # Check WAVE format
        if wav_data[8:12] != b'WAVE':
            return False
            
        # Check fmt chunk
        if wav_data[12:16] != b'fmt ':
            return False
            
        # Check data chunk
        data_chunk_pos = 36  # Standard position for data chunk
        if wav_data[data_chunk_pos:data_chunk_pos+4] != b'data':
            return False
            
        return True
        
    except Exception as e:
        logger.error(f"Error validating WAV format: {e}")
        return False

def get_wav_info(wav_data: bytes) -> dict:
    """
    Extract information from WAV file header.
    
    Args:
        wav_data: WAV file data
        
    Returns:
        Dictionary with WAV file information
    """
    try:
        if not validate_wav_format(wav_data):
            raise ValueError("Invalid WAV format")
            
        # Extract format information from header
        info = {
            'channels': struct.unpack('<H', wav_data[22:24])[0],
            'sample_rate': struct.unpack('<I', wav_data[24:28])[0],
            'byte_rate': struct.unpack('<I', wav_data[28:32])[0],
            'block_align': struct.unpack('<H', wav_data[32:34])[0],
            'bits_per_sample': struct.unpack('<H', wav_data[34:36])[0],
            'data_size': struct.unpack('<I', wav_data[40:44])[0],
            'total_size': len(wav_data)
        }
        
        # Calculate duration
        if info['byte_rate'] > 0:
            info['duration_seconds'] = info['data_size'] / info['byte_rate']
        else:
            info['duration_seconds'] = 0
            
        return info
        
    except Exception as e:
        logger.error(f"Error getting WAV info: {e}")
        return {} 