from dataclasses import dataclass
from config_manager import ConfigManager
from typing import Dict, List, Optional, Tuple
from decimal import Decimal
import json
from pathlib import Path

@dataclass
class LeagueFinances:
    """Constants for league financial structure"""
    def __init__(self, config: ConfigManager):
        self.BUY_IN = config.financial.buy_in
        self.FIRST_PLACE = config.financial.first_place
        self.SECOND_PLACE = config.financial.second_place
        self.THIRD_PLACE = config.financial.third_place
        self.SURVIVOR_BONUS = config.financial.survivor_bonus
        self.HIGH_POINTS_BONUS = config.financial.high_points_bonus
        self.SKINS_WEEKLY_POT = config.financial.skins_weekly_pot
    
    @property
    def total_guaranteed_payouts(self) -> Decimal:
        """Calculate total of all fixed payouts"""
        return (self.FIRST_PLACE + self.SECOND_PLACE + self.THIRD_PLACE + 
                self.SURVIVOR_BONUS + self.HIGH_POINTS_BONUS)
    
    @property
    def total_guaranteed_payouts(self) -> Decimal:
        """Calculate total of all fixed payouts"""
        return (self.FIRST_PLACE + self.SECOND_PLACE + self.THIRD_PLACE + 
                self.SURVIVOR_BONUS + self.HIGH_POINTS_BONUS)

class LeagueAccounting:
    def __init__(self, storage_manager, config: ConfigManager, yahoo_api=None):
        self.storage = storage_manager
        self.yahoo_api = yahoo_api
        self.finances = LeagueFinances(config)
        self.payments: Dict[str, Decimal] = {}
        self.total_collected = Decimal('0.00')
        self.load_payment_status()

    def process_survivor_bonus(self) -> Optional[str]:
        """Process survivor bonus competition"""
        print("\n" + "*" * 40 + " Survivor Results " + "*" * 40)
        
        all_weeks_data = []
        for week in range(1, 14):
            week_data = self.storage.load_data(f'week_{week}_matchup.json')
            if week_data:
                all_weeks_data.append(week_data)

        teams_info = self.storage.load_data('teams_info.json')
        if not teams_info:
            print("[!] No teams info found")
            return None

        active_teams = {team['team_key']: team['team_name'] for team in teams_info}

        for week_data in all_weeks_data:
            if not week_data:
                continue

            scores = {}
            for matchup in week_data:
                if matchup['team_key'] in active_teams:
                    scores[matchup['team_key']] = float(matchup['team_points'])
                if matchup['opponent_team_key'] in active_teams:
                    scores[matchup['opponent_team_key']] = float(matchup['opponent_points'])

            if not scores:
                continue

            lowest_team_key = min(scores, key=scores.get)
            lowest_team_name = active_teams[lowest_team_key]
            lowest_score = scores[lowest_team_key]

            print(f"[*] Week {week_data[0]['week']} eliminated: {lowest_team_name} with {lowest_score} points")
            del active_teams[lowest_team_key]

            if len(active_teams) == 1:
                winner_key = next(iter(active_teams))
                winner_name = active_teams[winner_key]
                print(f"[+] Survivor bonus winner: {winner_name}!")
                self.storage.save_data('survivor.json', {
                    'winner': winner_name,
                    'bonus': float(self.finances.SURVIVOR_BONUS)
                })
                return winner_name
            
        return None
    def generate_balance_sheet(self) -> str:
        """Generate a detailed balance sheet showing dues and winnings for each team"""
        # Get all winnings
        all_winnings = self.calculate_all_winnings()
        
        # Get all teams from latest standings or matchup data
        all_teams = set()
        # Check matchup data for weeks 1-13 to get all team names
        for week in range(1, 14):
            week_data = self.storage.load_data(f'week_{week}_matchup.json')
            if week_data:
                for matchup in week_data:
                    all_teams.add(matchup['team_name'])
                    all_teams.add(matchup['opponent_name'])
        
        # Create balance sheet entries
        report = []
        report.append("\n" + "="*80)
        report.append("LEAGUE BALANCE SHEET")
        report.append("="*80)
        
        # Header
        report.append("\n{:<25} {:>12} {:>12} {:>12} {:>12}".format(
            "Team", "Dues", "Winnings", "Balance", "Status"
        ))
        report.append("-"*80)
        
        # Track totals
        total_dues = Decimal('0.00')
        total_winnings = Decimal('0.00')
        
        # Generate entries for each team
        for team in sorted(all_teams):
            dues = self.finances.BUY_IN
            winnings = all_winnings.get(team, Decimal('0.00'))
            balance = winnings - dues
            
            # Determine status
            if balance > 0:
                status = "DUE TO RECEIVE"
            else:
                status = "NEEDS TO PAY"
                
            report.append("{:<25} {:>12.2f} {:>12.2f} {:>12.2f} {:>12}".format(
                team,
                dues,
                winnings,
                balance,
                status
            ))
            
            # Update totals
            total_dues += dues
            total_winnings += winnings
        
        # Add totals
        report.append("-"*80)
        report.append("{:<25} {:>12.2f} {:>12.2f} {:>12.2f}".format(
            "TOTALS", total_dues, total_winnings, total_winnings - total_dues
        ))
        
        # Add summary
        report.append("\nSUMMARY:")
        report.append(f"Total League Dues: ${total_dues:.2f}")
        report.append(f"Total Payouts: ${total_winnings:.2f}")
        report.append(f"Net Balance: ${(total_winnings - total_dues):.2f}")
        
        return "\n".join(report)

    def get_playoff_winnings(self) -> Dict[str, Decimal]:
        """Get playoff winnings based on final standings"""
        if not self.yahoo_api:
            return {}
        
        # Get game key and league ID from league key format "449.l.410864"
        game_key = "449"  # Hard-coded from your league key
        league_id = "410864"  # Hard-coded from your league key
        
        standings = self.yahoo_api.get_final_standings(game_key, league_id)
        if not standings:
            return {}
            
        winnings = {}
        payouts = {
            1: self.finances.FIRST_PLACE,
            2: self.finances.SECOND_PLACE,
            3: self.finances.THIRD_PLACE
        }
        
        for team in standings:
            winnings[team['name']] = payouts[team['rank']]
            
        return winnings

    def load_payment_status(self) -> None:
        """Load existing payment status or initialize new"""
        payment_data = self.storage.load_data('payments.json')
        if payment_data:
            self.payments = {k: Decimal(str(v)) for k, v in payment_data.items()}
            self.total_collected = sum(self.payments.values())

    def record_payment(self, team_name: str, amount: Decimal) -> None:
        """Record a payment from a team"""
        self.payments[team_name] = amount
        self.total_collected += amount
        self.storage.save_data('payments.json', 
                             {k: str(v) for k, v in self.payments.items()})

    def calculate_total_points(self) -> Dict[str, float]:
        """Calculate total points for each team from weekly data"""
        team_points = {}
        
        # Process weeks 1-13 (regular season)
        for week in range(1, 14):
            week_data = self.storage.load_data(f'week_{week}_matchup.json')
            if not week_data:
                continue
                
            for matchup in week_data:
                # Add team points
                team_name = matchup['team_name']
                if team_name not in team_points:
                    team_points[team_name] = 0.0
                team_points[team_name] += float(matchup['team_points'])
                
                # Add opponent points
                opp_name = matchup['opponent_name']
                if opp_name not in team_points:
                    team_points[opp_name] = 0.0
                team_points[opp_name] += float(matchup['opponent_points'])
        
        return team_points

    def get_highest_points_winner(self) -> Optional[Tuple[str, float]]:
        """Get the team with the highest total points through week 13"""
        total_points = self.calculate_total_points()
        if not total_points:
            return None
        return max(total_points.items(), key=lambda x: x[1])

    def calculate_skins_winnings(self) -> Dict[str, Decimal]:
        """Get total skins winnings per team from stored results"""
        skins_data = self.storage.load_data('skins_winners.json')
        if not skins_data:
            return {}
            
        team_totals = {}
        for team, wins in skins_data.items():
            # Skip malformed entries
            if not isinstance(wins, list):
                continue
            # Sum up all pot winnings for this team
            team_totals[team] = sum(Decimal(str(win['pot_winnings'])) for win in wins)
        
        return team_totals

    def generate_skins_report(self) -> str:
        """Generate detailed skins report"""
        report = []
        report.append("\nSKINS BREAKDOWN:")
        report.append("-" * 20)
        
        # Load raw skins data for detailed info
        skins_data = self.storage.load_data('skins_winners.json')
        if not skins_data:
            report.append("No skins winners recorded")
            return "\n".join(report)
        
        # Sort by week number for chronological display
        sorted_wins = []
        for team, wins in skins_data.items():
            # Skip malformed entries
            if not isinstance(wins, list):
                continue
            # Process each win for this team
            for win in wins:
                sorted_wins.append({
                    'team': team,
                    'week': win['week_number'],
                    'margin': win['margin_victory'],
                    'pot': win['pot_winnings']
                })
        sorted_wins.sort(key=lambda x: x['week'])
        
        # Display each win
        for win in sorted_wins:
            report.append(
                f"Week {win['week']}: {win['team']} "
                f"(margin: {win['margin']:.2f}, pot: ${win['pot']:.2f})"
            )
        
        # Show total winnings per team using existing calculate_skins_winnings method
        team_totals = self.calculate_skins_winnings()
        
        if team_totals:
            report.append("\nTOTAL SKINS WINNINGS:")
            for team, total in sorted(team_totals.items(), key=lambda x: x[1], reverse=True):
                report.append(f"{team}: ${total:.2f}")
        
        return "\n".join(report)

    def get_survivor_winner(self) -> Optional[str]:
        """Get the survivor pool winner"""
        # First try to get from stored survivor data
        survivor_data = self.storage.load_data('survivor.json')
        if survivor_data and 'winner' in survivor_data:
            return survivor_data['winner']
        
        # If not stored, calculate from weekly data
        active_teams = set()
        
        # Process each week to track eliminations
        for week in range(1, 14):
            week_data = self.storage.load_data(f'week_{week}_matchup.json')
            if not week_data:
                continue
                
            # First week, initialize active teams
            if week == 1:
                active_teams = {matchup['team_name'] for matchup in week_data}
                continue
            
            # Get scores for active teams
            scores = {}
            for matchup in week_data:
                if matchup['team_name'] in active_teams:
                    scores[matchup['team_name']] = float(matchup['team_points'])
            
            if scores:
                # Eliminate lowest scoring team
                eliminated = min(scores.items(), key=lambda x: x[1])[0]
                active_teams.remove(eliminated)
                
                # If only one team remains, they're the winner
                if len(active_teams) == 1:
                    winner = next(iter(active_teams))
                    # Store for future reference
                    self.storage.save_data('survivor.json', {
                        'winner': winner,
                        'bonus': float(self.finances.SURVIVOR_BONUS)
                    })
                    return winner
        
            return None

    def calculate_all_winnings(self) -> Dict[str, Decimal]:
        winnings = {}
        
        # Add playoff winnings
        playoff_winnings = self.get_playoff_winnings()
        for team, amount in playoff_winnings.items():
            winnings[team] = winnings.get(team, Decimal('0.00')) + amount
        
        # Skins winnings
        skins_winnings = self.calculate_skins_winnings()
        for team, amount in skins_winnings.items():
            winnings[team] = winnings.get(team, Decimal('0.00')) + amount
            
        # Survivor bonus
        survivor_winner = self.get_survivor_winner()
        if survivor_winner:
            winnings[survivor_winner] = (
                winnings.get(survivor_winner, Decimal('0.00')) + 
                self.finances.SURVIVOR_BONUS
            )
            
        # Highest points bonus
        points_winner = self.get_highest_points_winner()
        if points_winner:
            team_name, _ = points_winner
            winnings[team_name] = (
                winnings.get(team_name, Decimal('0.00')) + 
                self.finances.HIGH_POINTS_BONUS
            )
        
        return winnings

    def generate_financial_report(self) -> str:
        """Generate a detailed financial report"""
        report = []
        report.append("\n" + "="*60)
        report.append("LEAGUE FINANCIAL REPORT")
        report.append("="*60 + "\n")

        # Regular Season Bonuses
        report.append("REGULAR SEASON BONUSES:")
        report.append("-"*20)
        
        # Skins Winners (with counts)
        skins = self.calculate_skins_winnings()
        if skins:
            report.append("\nSkins Winners:")
            for team, amount in sorted(skins.items(), key=lambda x: x[1], reverse=True):
                weeks_won = int(amount / 10)  # Calculate number of weeks won
                report.append(f"  {team}: ${amount:.2f} ({weeks_won} {'week' if weeks_won == 1 else 'weeks'})")

        # Survivor Winner
        survivor = self.get_survivor_winner()
        if survivor:
            report.append(f"\nSurvivor Bonus Winner: {survivor} (${self.finances.SURVIVOR_BONUS:.2f})")
        
        # Points Winner
        points_winner = self.get_highest_points_winner()
        if points_winner:
            team, points = points_winner
            report.append(f"\nHighest Points Winner: {team} - {points:.2f} points (${self.finances.HIGH_POINTS_BONUS:.2f})")

        # Calculate totals
        winnings = self.calculate_all_winnings()
        
        # Final Totals
        report.append("\nFINAL WINNINGS:")
        report.append("-"*20)
        for team, amount in sorted(winnings.items(), key=lambda x: x[1], reverse=True):
            if amount > 0:
                report.append(f"{team}: ${amount:.2f}")

        return "\n".join(report)



if __name__ == "__main__":
    from storage_manager import StorageManager
    from yahoo_api import YahooFantasyAPI
    from config_manager import ConfigManager
    import os
    
    try:
        # Setup Yahoo API with authentication
        client_id = os.environ['YAHOO_CLIENT_ID']
        client_secret = os.environ['YAHOO_CLIENT_SECRET']
        yahoo_api = YahooFantasyAPI(client_id, client_secret)
        
        # Ensure API is authenticated
        if not yahoo_api.verify_league_access():
            print("[!] Failed to verify league access")
            exit(1)
            
        storage = StorageManager()
        config = ConfigManager()  # Create ConfigManager instance
        accounting = LeagueAccounting(storage, config, yahoo_api)  # Pass config as second parameter
        
        # Print both reports
        print(accounting.generate_financial_report())
        print("\n" + "="*80)
        print(accounting.generate_balance_sheet())
        
    except KeyError as e:
        print(f"[!] Missing environment variable: {e}")
    except Exception as e:
        print(f"[!] An error occurred: {e}")