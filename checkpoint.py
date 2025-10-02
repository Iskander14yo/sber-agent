import json
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime

@dataclass
class ProcessStats:
    total_alerts: int = 0
    current_stage: str = "initializing"
    stage_progress: float = 0.0
    tokens_processed: int = 0
    avg_tokens_per_item: float = 0.0
    filtered_count: int = 0
    last_update: str = datetime.now().isoformat()
    error_count: int = 0
    current_feed: str = ""
    stage_details: str = ""

class CheckpointManager:
    def __init__(self, checkpoint_dir: str = ".checkpoints"):
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(exist_ok=True)
        self.current_run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.stats = ProcessStats()
        
    def _get_checkpoint_path(self) -> Path:
        return self.checkpoint_dir / f"checkpoint_{self.current_run_id}.json"
    
    def update_stats(self, **kwargs) -> None:
        for key, value in kwargs.items():
            if hasattr(self.stats, key):
                setattr(self.stats, key, value)
        self.stats.last_update = datetime.now().isoformat()
        self.save_checkpoint()
    
    def save_checkpoint(self) -> None:
        checkpoint_data = asdict(self.stats)
        self._get_checkpoint_path().write_text(json.dumps(checkpoint_data, indent=2))
    
    def load_latest_checkpoint(self) -> Optional[Dict[str, Any]]:
        try:
            latest_checkpoint = max(self.checkpoint_dir.glob("checkpoint_*.json"), 
                                  key=lambda x: x.stat().st_mtime)
            return json.loads(latest_checkpoint.read_text())
        except (ValueError, FileNotFoundError):
            return None

    def get_current_stats(self) -> Dict[str, Any]:
        return asdict(self.stats)

# Stage constants for consistent stage naming
STAGES = {
    "INIT": "Initializing",
    "RSS_FETCH": "Fetching RSS Feeds",
    "FIRST_FILTER": "First-pass Content Filtering",
    "CONTENT_FETCH": "Fetching Full Content",
    "SECOND_FILTER": "Second-pass Content Analysis",
    "FINAL": "Finalizing Results"
}
