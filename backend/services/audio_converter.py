"""
FarmAI Audio Converter Service
Converts generated WAV audio files into WhatsApp-compatible OGG OPUS files using ffmpeg if available.
"""

import os
import subprocess
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def convert_wav_to_ogg_opus(wav_path: str) -> dict:
    """
    Attempts to convert a WAV file to OGG OPUS using ffmpeg.
    
    Parameters
    ----------
    wav_path : str
        Absolute path to the source WAV file.
        
    Returns
    -------
    dict with keys: success, filename, error_message
    """
    try:
        wav_file_path = Path(wav_path)
        if not wav_file_path.is_file() or wav_file_path.stat().st_size == 0:
            return {
                "success": False,
                "error_message": f"WAV file not found or is empty at: {wav_path}"
            }
            
        # Define target OGG file path in the same directory
        ogg_filename = wav_file_path.stem + ".ogg"
        ogg_file_path = wav_file_path.parent / ogg_filename
        
        # Check if ffmpeg is available
        # We run it via subprocess to avoid crashes and check its output
        try:
            # Run ffmpeg conversion
            # -y overwrites output, -c:a libopus uses opus codec, -b:a 16k uses low bitrate suitable for voice
            cmd = [
                "ffmpeg", "-y",
                "-i", str(wav_file_path),
                "-c:a", "libopus",
                "-b:a", "16k",
                str(ogg_file_path)
            ]
            logger.info("Executing audio conversion: %s", " ".join(cmd))
            
            # Use subprocess.run with a timeout to prevent locking
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=15
            )
            
            if result.returncode == 0 and ogg_file_path.is_file() and ogg_file_path.stat().st_size > 0:
                logger.info("Successfully converted audio to OGG OPUS: %s", ogg_file_path)
                return {
                    "success": True,
                    "filename": ogg_filename
                }
            else:
                err_msg = result.stderr or "ffmpeg returned non-zero code or output file is empty"
                logger.warning("ffmpeg audio conversion failed: %s", err_msg)
                return {
                    "success": False,
                    "error_message": f"ffmpeg failed: {err_msg}"
                }
                
        except FileNotFoundError:
            logger.warning("ffmpeg executable not found in system PATH. Falling back to WAV.")
            return {
                "success": False,
                "error_message": "ffmpeg executable not found in system PATH."
            }
        except subprocess.TimeoutExpired:
            logger.error("ffmpeg conversion timed out after 15 seconds.")
            return {
                "success": False,
                "error_message": "ffmpeg conversion timed out."
            }
            
    except Exception as exc:
        logger.exception("Unexpected error during audio conversion: %s", exc)
        return {
            "success": False,
            "error_message": str(exc)
        }
