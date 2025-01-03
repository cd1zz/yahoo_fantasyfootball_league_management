import os
from typing import List, Dict, Optional
from decimal import Decimal
from yahoo_api import YahooFantasyAPI
from accounting import LeagueAccounting
from storage_manager import StorageManager
from config_manager import ConfigManager
import argparse
from pathlib import Path

# Add this at the top with your other imports
def get_default_config_path() -> Path:
    """Get the default config path relative to the script directory"""
    return Path(__file__).parent / 'config.yaml'

def setup_apis() -> tuple[YahooFantasyAPI, StorageManager]:
    """Setup API and storage connections"""
    try:
        # Yahoo API setup
        client_id = os.environ['YAHOO_CLIENT_ID']
        client_secret = os.environ['YAHOO_CLIENT_SECRET']
        yahoo_api = YahooFantasyAPI(client_id, client_secret)
        
        # Storage setup
        storage = StorageManager()
        
        return yahoo_api, storage
    except KeyError as e:
        raise EnvironmentError(f"Missing environment variable: {e}")

def get_week_input() -> Optional[str]:
    """Get and validate week input from user"""
    while True:
        user_input = input("[?] Enter week # or 'a' for all (weeks 1-13): ")
        if user_input.lower() == 'a':
            return 'a'
        try:
            week = int(user_input)
            if 1 <= week <= 13:
                return str(week)
            print('[!] Error. Weeks should be 1 - 13 only.')
        except ValueError:
            print('[!] Error. Enter valid week number or "a" for all.')

def process_matchups(yahoo_api: YahooFantasyAPI, storage: StorageManager, week: str):
    """Process matchups for specified week(s)"""
    teams_info = storage.load_data('teams_info.json')
    if not teams_info:
        print("[!] No teams info found. Fetching from Yahoo...")
        game_key = yahoo_api.get_game_key()
        if not game_key:
            print("[!] Failed to get game key")
            return
        teams_info = yahoo_api.get_team_info(game_key, "410864")  # Ulster Nation XIV
        storage.save_data('teams_info.json', teams_info)

    weeks_to_process = range(1, 14) if week == 'a' else [int(week)]
    
    for current_week in weeks_to_process:
        print(f"\n{'-' * 40} Week {current_week} {'-' * 40}")
        matchup_results = []
        
        for team in teams_info:
            team_key = team["team_key"]
            matchup_data = yahoo_api.get_matchup_results(team_key, current_week)
            
            if not matchup_data:
                continue
                
            # Check if week is completed
            if matchup_data['matchup']['status'] != 'postevent':
                print(f"[!] Week {current_week} is not over yet.")
                break
                
            process_single_matchup(matchup_data, team, matchup_results)
            
        if matchup_results:
            storage.save_data(f'week_{current_week}_matchup.json', matchup_results)

def process_single_matchup(matchup_data: Dict, team: Dict, matchup_results: List):
    """Process a single matchup and add to results if not already processed"""
    matchup = matchup_data['matchup']['0']['teams']
    team_points = float(matchup['0']['team'][1]['team_points']['total'])
    opponent_points = float(matchup['1']['team'][1]['team_points']['total'])
    opponent_name = matchup['1']['team'][0][2]['name']
    opponent_team_key = matchup['1']['team'][0][0]['team_key']
    
    # Check if matchup already processed
    team_exists = any(m['team_name'] == team['team_name'] or m['opponent_name'] == team['team_name'] 
                     for m in matchup_results)
    
    if not team_exists:
        # Calculate winner and margin
        if team_points > opponent_points:
            margin = str(round(team_points - opponent_points, 2))
            winning_team = team['team_name']
            print(f"\033[32m{team['team_name']} {team_points}\033[0m vs {opponent_name} {opponent_points}")
            print(f"---> {team['team_name']} wins by: {margin}\n")
        elif opponent_points > team_points:
            margin = str(round(opponent_points - team_points, 2))
            winning_team = opponent_name
            print(f"{team['team_name']} {team_points} vs \033[32m{opponent_name} {opponent_points}\033[0m")
            print(f"---> {opponent_name} wins by: {margin}\n")
        else:
            margin = "tie"
            winning_team = "tie"
            print(f"\033[31m{team['team_name']} {team_points} vs {opponent_name} {opponent_points}\033[0m\n")

        matchup_results.append({
            "team_key": team['team_key'],
            "team_name": team['team_name'],
            "week": matchup_data['matchup']['week'],
            "team_points": str(team_points),
            "opponent_points": str(opponent_points),
            "opponent_name": opponent_name,
            "opponent_team_key": opponent_team_key,
            "margin_victory": margin,
            "winning_team": winning_team
        })

def calculate_skins_winnings(storage: StorageManager, config: ConfigManager):
    """Calculate total skins winnings per team based on rolling pot"""
    print("\n" + "*" * 40 + " Skins Results " + "*" * 40)
    
    skins_winners = {}
    current_pot = Decimal(str(config.financial.skins_weekly_pot))  # Initial pot value
    
    # Process weeks 1-17 (full season)
    for week in range(1, 18):
        week_data = storage.load_data(f'week_{week}_matchup.json')
        if not week_data:
            continue
            
        # Find potential winners (margin >= 20)
        potential_winners = {}
        for matchup in week_data:
            try:
                margin = Decimal(str(matchup['margin_victory']))
                if margin >= config.game.skins_min_margin:
                    winning_team = matchup['winning_team']
                    if winning_team not in potential_winners or margin > potential_winners[winning_team]['margin']:
                        potential_winners[winning_team] = {
                            'margin': margin,
                            'week': week
                        }
            except (ValueError, KeyError):
                continue  # Skip invalid entries
                
        if not potential_winners:
            # No winner this week, pot increases
            current_pot += Decimal(str(config.financial.skins_weekly_pot))
            continue
            
        # Get winner with highest margin
        winner = max(potential_winners.items(), key=lambda x: x[1]['margin'])
        winner_team, winner_data = winner
        
        # Record win in skins_winners
        if winner_team not in skins_winners:
            skins_winners[winner_team] = []
            
        skins_winners[winner_team].append({
            'week_number': week,
            'margin_victory': float(winner_data['margin']),
            'pot_winnings': float(current_pot)
        })
        
        print(f"[*] Skins winner for week {week}: {winner_team} by {round(float(winner_data['margin']), 2)}")
        
        # Save updated skins data
        storage.save_data('skins_winners.json', skins_winners)
        
        # Reset pot for next week
        current_pot = Decimal(str(config.financial.skins_weekly_pot))


def main():
    try:
        # Setup command line arguments
        parser = argparse.ArgumentParser(description='Fantasy Football League Manager')
        parser.add_argument('--config', type=Path, default=get_default_config_path(),
                          help='Path to config.yaml file')
        args = parser.parse_args()

        # Load configuration
        config = ConfigManager(args.config)
        
        # Setup
        yahoo_api, storage = setup_apis()
        
        # Initialize accounting with config
        accounting = LeagueAccounting(storage, config, yahoo_api)
        
        # Verify access
        if not yahoo_api.verify_league_access():
            print("[!] Unable to access league")
            return
            
        # Get week to process
        week = get_week_input()
    
        # Process weekly data
        process_matchups(yahoo_api, storage, week)
        
        # Calculate bonuses if enabled
        if config.game.skins_game_enabled:
            calculate_skins_winnings(storage, config)
            
        if config.game.survivor_pool_enabled:
            accounting.process_survivor_bonus()

        # Export season data
        storage.export_season_data()
        
        print("[*] Complete!")
        
    except Exception as e:
        print(f"[!] An error occurred: {e}")
        raise

if __name__ == "__main__":
    main()
