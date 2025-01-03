from dataclasses import dataclass
from typing import Optional
from pathlib import Path
import yaml
from decimal import Decimal

@dataclass
class LeagueConfig:
    """League-specific configuration"""
    league_id: str

@dataclass
class FinancialConfig:
    """Financial structure configuration"""
    buy_in: float
    first_place: float
    second_place: float
    third_place: float
    survivor_bonus: float
    high_points_bonus: float
    skins_weekly_pot: float
    
    def to_decimal(self) -> None:
        """Convert all float values to Decimal"""
        self.buy_in = Decimal(str(self.buy_in))
        self.first_place = Decimal(str(self.first_place))
        self.second_place = Decimal(str(self.second_place))
        self.third_place = Decimal(str(self.third_place))
        self.survivor_bonus = Decimal(str(self.survivor_bonus))
        self.high_points_bonus = Decimal(str(self.high_points_bonus))
        self.skins_weekly_pot = Decimal(str(self.skins_weekly_pot))

@dataclass
class GameConfig:
    """Game-specific rules configuration"""
    skins_min_margin: float
    survivor_pool_enabled: bool
    skins_game_enabled: bool

class ConfigManager:
    """Manages loading and validation of configuration"""
    
    def __init__(self, config_path: Path = Path(".\config.yaml")):
        self.config_path = config_path
        self.league: LeagueConfig
        self.financial: FinancialConfig
        self.game: GameConfig
        self._load_config()
    
    def _load_config(self) -> None:
        """Load configuration from YAML file"""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")
            
        with self.config_path.open('r') as f:
            config_data = yaml.safe_load(f)
            
        self.league = LeagueConfig(**config_data.get('league', {}))
        self.financial = FinancialConfig(**config_data.get('financial', {}))
        self.game = GameConfig(**config_data.get('game', {}))
        
        # Convert financial values to Decimal
        self.financial.to_decimal()
        
        if not self.validate():
            raise ValueError("Invalid configuration")
    
    def validate(self) -> bool:
        """Validate entire configuration"""
        if not self.league.league_id:
            raise ValueError("League ID must be specified")
        
        total_payouts = (
            self.financial.first_place + 
            self.financial.second_place + 
            self.financial.third_place + 
            self.financial.survivor_bonus + 
            self.financial.high_points_bonus
        )
        
        return True