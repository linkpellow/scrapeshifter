"""
Chimera Core - Storage Bridge

Handles trace file uploads to cloud storage.
For Railway deployment, traces are saved locally and can be uploaded to external storage.
"""

import os
import logging
from pathlib import Path
from typing import Optional
import tempfile
import shutil

logger = logging.getLogger(__name__)

# Storage configuration
TRACE_STORAGE_DIR = os.getenv("TRACE_STORAGE_DIR", "/tmp/chimera-traces")
UPLOAD_TO_CLOUD = os.getenv("UPLOAD_TRACES_TO_CLOUD", "false").lower() == "true"
CLOUD_STORAGE_URL = os.getenv("CLOUD_STORAGE_URL", "")


def ensure_trace_directory() -> Path:
    """
    Ensure trace storage directory exists.
    
    Returns:
        Path to trace directory
    """
    trace_dir = Path(TRACE_STORAGE_DIR)
    trace_dir.mkdir(parents=True, exist_ok=True)
    return trace_dir


def save_trace_locally(trace_path: Path, worker_id: str, mission_id: Optional[str] = None) -> Optional[str]:
    """
    Save trace file locally.
    
    Args:
        trace_path: Path to the trace file (from Playwright)
        worker_id: Worker identifier
        mission_id: Optional mission identifier
    
    Returns:
        Local file path if successful, None otherwise
    """
    try:
        trace_dir = ensure_trace_directory()
        
        # Generate filename
        if mission_id:
            filename = f"{worker_id}_{mission_id}.zip"
        else:
            import time
            timestamp = int(time.time())
            filename = f"{worker_id}_{timestamp}.zip"
        
        local_path = trace_dir / filename
        
        # Copy trace file to storage directory
        if trace_path.exists():
            shutil.copy2(trace_path, local_path)
            logger.info(f"✅ Trace saved locally: {local_path}")
            return str(local_path)
        else:
            logger.error(f"❌ Trace file not found: {trace_path}")
            return None
            
    except Exception as e:
        logger.error(f"❌ Failed to save trace locally: {e}")
        return None


def upload_trace_to_storage(trace_path: Path, worker_id: str, mission_id: Optional[str] = None) -> Optional[str]:
    """
    Upload trace file to cloud storage.
    
    For Railway deployment, this can be extended to upload to:
    - S3 (AWS)
    - Google Cloud Storage
    - Railway's storage service
    - Or any other cloud storage provider
    
    Args:
        trace_path: Path to the trace file (from Playwright)
        worker_id: Worker identifier
        mission_id: Optional mission identifier
    
    Returns:
        Cloud storage URL if successful, None otherwise
    """
    if not UPLOAD_TO_CLOUD:
        # Save locally only
        local_path = save_trace_locally(trace_path, worker_id, mission_id)
        if local_path:
            # Return local path as URL (can be accessed via Railway's file system or exposed endpoint)
            return f"file://{local_path}"
        return None
    
    # TODO: Implement cloud storage upload
    # For now, save locally and return local path
    local_path = save_trace_locally(trace_path, worker_id, mission_id)
    if local_path:
        logger.info(f"✅ Trace uploaded to storage: {local_path}")
        return f"file://{local_path}"
    
    return None


def cleanup_old_traces(max_age_days: int = 7) -> None:
    """
    Clean up old trace files.
    
    Args:
        max_age_days: Maximum age in days for trace files
    """
    try:
        trace_dir = ensure_trace_directory()
        import time
        
        current_time = time.time()
        max_age_seconds = max_age_days * 24 * 60 * 60
        
        for trace_file in trace_dir.glob("*.zip"):
            file_age = current_time - trace_file.stat().st_mtime
            if file_age > max_age_seconds:
                trace_file.unlink()
                logger.debug(f"🗑️ Cleaned up old trace: {trace_file.name}")
                
    except Exception as e:
        logger.error(f"❌ Failed to cleanup old traces: {e}")
