from typing import Optional, Dict, Any, List
import time
import json
from pathlib import Path
import requests
from requests_oauthlib import OAuth2Session

class YahooFantasyAPI:
    """Handles all interactions with Yahoo Fantasy Sports API"""
    
    BASE_URL = 'https://fantasysports.yahooapis.com/fantasy/v2'
    AUTH_URL = 'https://api.login.yahoo.com/oauth2/request_auth'
    TOKEN_URL = 'https://api.login.yahoo.com/oauth2/get_token'
    REDIRECT_URI = 'oob'
    SCOPE = 'fspt-r'
    
    def __init__(self, client_id: str, client_secret: str, token_file: str = 'token.json'):
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_file = Path(token_file)
        self.session: Optional[OAuth2Session] = None
        self.token: Optional[Dict] = None
        self._initialize_session()

    def _initialize_session(self) -> None:
        """Initialize OAuth session and load existing token if available"""
        self.token = self._load_token()
        self.session = OAuth2Session(
            self.client_id,
            redirect_uri=self.REDIRECT_URI,
            scope=self.SCOPE,
            token=self.token
        )

    def _load_token(self) -> Optional[Dict]:
        """Load token from file if it exists and is valid"""
        try:
            if self.token_file.exists():
                with self.token_file.open('r') as f:
                    token = json.load(f)
                if not self._is_token_expired(token):
                    return token
        except (json.JSONDecodeError, KeyError):
            pass
        return None

    def _save_token(self, token: Dict) -> None:
        """Save token to file"""
        with self.token_file.open('w') as f:
            json.dump(token, f, indent=4)

    def _is_token_expired(self, token: Dict) -> bool:
        """Check if token is expired"""
        # Add buffer of 5 minutes to prevent edge cases
        return time.time() > token.get('expires_at', 0) - 300

    def authenticate(self) -> None:
        """Handle complete authentication flow"""
        if self.token and not self._is_token_expired(self.token):
            return

        # Create new session for auth
        self.session = OAuth2Session(
            self.client_id,
            redirect_uri=self.REDIRECT_URI,
            scope=self.SCOPE
        )

        # Get authorization URL
        auth_url, _ = self.session.authorization_url(self.AUTH_URL)
        print('\n[*] Please authorize at:')
        print(auth_url)
        
        # Get authorization code from user
        auth_code = input('\n[?] Enter code: ').strip()
        
        # Get token
        self.token = self.session.fetch_token(
            self.TOKEN_URL,
            code=auth_code,
            client_secret=self.client_secret
        )
        
        self._save_token(self.token)

    def _make_request(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """Make authenticated request to Yahoo API"""
        if not params:
            params = {}
        params['format'] = 'json'

        # Ensure valid token
        if not self.token or self._is_token_expired(self.token):
            self.authenticate()

        url = f'{self.BASE_URL}/{endpoint}'
        
        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"[!] API request failed: {e}")
            if response.status_code == 401:
                # Token might be invalid, try to reauthenticate
                self.authenticate()
                response = self.session.get(url, params=params)
                response.raise_for_status()
                return response.json()
            raise

    def verify_league_access(self) -> bool:
        """Verify access to fantasy league"""
        try:
            response = self._make_request('users;use_login=1/games;game_keys=nfl/leagues')
            return bool(response.get('fantasy_content', {}).get('users'))
        except Exception as e:
            print(f"[!] League access verification failed: {e}")
            return False

    def get_game_key(self) -> Optional[str]:
        """Get current NFL game key"""
        try:
            response = self._make_request('game/nfl')
            return response['fantasy_content']['game'][0]['game_id']
        except (KeyError, IndexError) as e:
            print(f"[!] Failed to get game key: {e}")
            return None

    def get_team_info(self, game_id: str, league_id: str) -> list:
        """Get information for all teams in the league"""
        teams_info = []
        
        for team_index in range(1, 13):  # Assuming 12 teams
            team_key = f'{game_id}.l.{league_id}.t.{team_index}'
            try:
                response = self._make_request(f'team/{team_key}/matchups')
                team_data = response['fantasy_content']['team'][0]
                
                teams_info.append({
                    'team_key': team_data[0]['team_key'],
                    'team_id': team_data[1]['team_id'],
                    'team_name': team_data[2]['name']
                })
                print(f"[+] Successfully added {team_data[2]['name']}")
                
            except Exception as e:
                print(f"[!] Error processing team {team_index}: {e}")
                continue
                
        return teams_info

    def get_matchup_results(self, team_key: str, week: int) -> Optional[Dict]:
        """Get matchup results for a specific team and week"""
        try:
            response = self._make_request(f'team/{team_key}/matchups')
            matchup_data = response['fantasy_content']['team'][1]['matchups'][str(week-1)]
            return matchup_data
        except Exception as e:
            print(f"[!] Error getting matchup results: {e}")
            return None

    def get_final_standings(self, game_key: str, league_id: str) -> List[Dict]:
        """Get top 3 final standings from Yahoo"""
        league_key = f"{game_key}.l.{league_id}"
        url = f"{self.BASE_URL}/league/{league_key}/standings"
        
        try:
            response = self.session.get(url, params={'format': 'json'})
            response.raise_for_status()
            
            data = response.json()
            standings_data = data['fantasy_content']['league'][1]['standings'][0]['teams']
            
            # Process all teams and sort by rank
            all_teams = []
            for team_id, team_data in standings_data.items():
                if team_id == 'count':  # Skip the count field
                    continue
                    
                try:
                    team = team_data['team']
                    name = team[0][2]['name']  # Access name from the nested array
                    rank = int(team[2]['team_standings']['rank'])  # Access rank from team_standings object
                    team_key = team[0][0]['team_key']
                    
                    all_teams.append({
                        'rank': rank,
                        'name': name,
                        'team_key': team_key
                    })
                except Exception as e:
                    print(f"Error processing team {team_id}: {e}")
                    continue
            
            # Sort by rank and get top 3
            all_teams.sort(key=lambda x: x['rank'])
            return all_teams[:3]
            
        except Exception as e:
            print(f"[!] Error getting standings: {e}")
            return []        
    def get_playoff_results(self, league_key: str) -> List[Dict]:
        url = f"{self.BASE_URL}/league/{league_key}/scoreboard;week=16"
        response = self.session.get(url)
        if response.status_code != 200:
            return []
            
        matchups = response.json()['fantasy_content']['league'][1]['scoreboard']['0']['matchups']
        playoff_teams = []
        
        for matchup in matchups:
            if matchup.get('is_playoffs') and matchup.get('playoff_tier'):
                teams = matchup['teams']
                team1 = teams['0']['team']
                team2 = teams['1']['team']
                
                if matchup['playoff_tier'] == 1:  # Championship
                    winner = team1 if float(team1[1]['team_points']) > float(team2[1]['team_points']) else team2
                    loser = team2 if winner == team1 else team1
                    playoff_teams.extend([
                        {'rank': 1, 'name': winner[2]['name']},
                        {'rank': 2, 'name': loser[2]['name']}
                    ])
                elif matchup['playoff_tier'] == 2:  # Third place
                    winner = team1 if float(team1[1]['team_points']) > float(team2[1]['team_points']) else team2
                    playoff_teams.append({'rank': 3, 'name': winner[2]['name']})
        
        return playoff_teams

# Example usage:
if __name__ == "__main__":
    import os
    
    # Get credentials from environment
    client_id = os.environ.get('YAHOO_CLIENT_ID')
    client_secret = os.environ.get('YAHOO_CLIENT_SECRET')
    
    if not (client_id and client_secret):
        raise EnvironmentError("YAHOO_CLIENT_ID and YAHOO_CLIENT_SECRET must be set")
    
    # Initialize API
    yahoo = YahooFantasyAPI(client_id, client_secret)
    
    # Verify access
    if yahoo.verify_league_access():
        print("[+] Successfully connected to Yahoo Fantasy API")
        
        # Get game key
        game_key = yahoo.get_game_key()
        if game_key:
            print(f"[+] Current NFL game key: {game_key}")
