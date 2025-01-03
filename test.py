from yahoo_api import YahooFantasyAPI
import os
import json

def test_league_standings():
    # Initialize API with credentials
    client_id = os.environ.get('YAHOO_CLIENT_ID')
    client_secret = os.environ.get('YAHOO_CLIENT_SECRET')
    
    if not (client_id and client_secret):
        raise EnvironmentError("YAHOO_CLIENT_ID and YAHOO_CLIENT_SECRET must be set")
    
    # Initialize API
    yahoo = YahooFantasyAPI(client_id, client_secret)
    
    # Ensure we're authenticated
    yahoo.authenticate()
    
    # Make request to standings endpoint using your league key
    url = "https://fantasysports.yahooapis.com/fantasy/v2/league/449.l.410864/standings"
    response = yahoo.session.get(url, params={'format': 'json'})
    
    # Check if request was successful
    if response.status_code == 200:
        # Pretty print the JSON response
        print("\nStandings Response:")
        print(json.dumps(response.json(), indent=2))
    else:
        print(f"Error: {response.status_code}")
        print(f"Response: {response.text}")
        
    # Let's also try to get the scoreboard for week 16 (likely championship week)
    scoreboard_url = "https://fantasysports.yahooapis.com/fantasy/v2/league/449.l.410864/scoreboard;week=16"
    scoreboard_response = yahoo.session.get(scoreboard_url, params={'format': 'json'})
    
    if scoreboard_response.status_code == 200:
        print("\nWeek 16 Scoreboard Response:")
        print(json.dumps(scoreboard_response.json(), indent=2))
    else:
        print(f"Error getting scoreboard: {scoreboard_response.status_code}")
        print(f"Response: {scoreboard_response.text}")

if __name__ == "__main__":
    test_league_standings()