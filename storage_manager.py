from pathlib import Path
import json
from typing import Any, Optional
from datetime import datetime
import shutil

class StorageManager:
    """Manages local storage for fantasy football league data"""
    
    def __init__(self, base_dir: str = "league_data"):
        self.base_dir = Path(base_dir)
        self.backup_dir = self.base_dir / "backups"
        self._ensure_directories()
    
    def _ensure_directories(self) -> None:
        """Create necessary directories if they don't exist"""
        self.base_dir.mkdir(exist_ok=True)
        self.backup_dir.mkdir(exist_ok=True)
    
    def _create_backup(self, file_path: Path) -> None:
        """Create a backup of a file before modification"""
        if not file_path.exists():
            return
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self.backup_dir / f"{file_path.stem}_{timestamp}{file_path.suffix}"
        shutil.copy2(file_path, backup_path)
        
        # Clean up old backups (keep last 5)
        backups = sorted(self.backup_dir.glob(f"{file_path.stem}_*{file_path.suffix}"))
        for old_backup in backups[:-5]:
            old_backup.unlink()
    
    def save_data(self, filename: str, data: Any) -> None:
        """Save data to JSON file with backup"""
        file_path = self.base_dir / filename
        self._create_backup(file_path)
        
        with file_path.open('w') as f:
            json.dump(data, f, indent=4, default=str)
    
    def load_data(self, filename: str) -> Optional[Any]:
        """Load data from JSON file"""
        file_path = self.base_dir / filename
        
        try:
            with file_path.open('r') as f:
                return json.load(f)
        except FileNotFoundError:
            return None
        except json.JSONDecodeError as e:
            print(f"Error reading {filename}: {e}")
            # Attempt to restore from latest backup
            return self._restore_from_backup(filename)
    
    def _restore_from_backup(self, filename: str) -> Optional[Any]:
        """Attempt to restore data from most recent backup"""
        backups = sorted(self.backup_dir.glob(f"{Path(filename).stem}_*{Path(filename).suffix}"))
        
        if not backups:
            return None
            
        latest_backup = backups[-1]
        try:
            with latest_backup.open('r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return None
    
    def list_weeks_data(self) -> list[str]:
        """List all available week data files"""
        return sorted([f.name for f in self.base_dir.glob("week_*.json")])
    
    def export_season_data(self) -> None:
        """Export all season data to a single file"""
        season_data = {
            'teams': self.load_data('teams_info.json'),
            'weeks': {},
            'skins': self.load_data('skins_winners.json'),
            'timestamp': datetime.now().isoformat()
        }
        
        # Collect all week data
        for week_file in sorted(self.base_dir.glob("week_*.json")):
            week_num = week_file.stem.split('_')[1]
            season_data['weeks'][week_num] = self.load_data(week_file.name)
        
        # Save as single season file
        season_file = f"season_{datetime.now().year}.json"
        self.save_data(season_file, season_data)

# Example usage:
if __name__ == "__main__":
    storage = StorageManager()
    
    # Save some data
    storage.save_data('teams_info.json', {'team1': {'name': 'Vikings'}})
    
    # Load data
    teams = storage.load_data('teams_info.json')
    
    # Export season
    storage.export_season_data()
