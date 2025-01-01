import inspect
import requests
import time
import json
import sys
import os
from requests_oauthlib import OAuth2Session
from githubapi import GitHubAPI

# Global Constants
BASE_URL = 'https://fantasysports.yahooapis.com/fantasy/v2'

# Load our secret tokens from environment variables/
try:
    CLIENT_ID = os.environ['YAHOO_CLIENT_ID']  # AKA Consumer Key
except KeyError:
    raise EnvironmentError(
        "[!] The environment variable YAHOO_CLIENT_ID is not set. Also known as the 'Consumer Key.'")

try:
    CLIENT_SECRET = os.environ['YAHOO_CLIENT_SECRET']  # AKA Consumer Secret'
except KeyError:
    raise EnvironmentError(
        "[!] The environment variable YAHOO_CLIENT_SECRET is not set. Also known as the 'Consumer Secret.'")

REDIRECT_URI = 'oob'
SCOPE = 'fspt-r'
DEBUG = True

def verify_league_access(headers):
    """Verify access to fantasy league"""
    url = f'{BASE_URL}/users;use_login=1/games;game_keys=nfl/leagues'
    print(f"[DEBUG] Checking league access with URL: {url}")
    print(f"[DEBUG] Headers: {headers}")
    
    response = requests.get(url, headers=headers, params={'format': 'json'})
    if response.status_code != 200:
        print(f"[!] League access check failed: {response.status_code}")
        print(json.dumps(response.json(), indent=2))
        return False
        
    data = response.json()
    print("[DEBUG] League access response:")
    print(json.dumps(data, indent=2))
    return True

def get_new_oauth_token():
    yahoo = OAuth2Session(CLIENT_ID, redirect_uri=REDIRECT_URI, scope=SCOPE)
    authorization_url, state = yahoo.authorization_url(
        'https://api.login.yahoo.com/oauth2/request_auth')

    print('[*] Please authorize at:')
    print(authorization_url)
    
    authorization_code = input('[?] Enter code: ')
    
    print("[DEBUG] Getting token with code:", authorization_code)
    token = yahoo.fetch_token(
        'https://api.login.yahoo.com/oauth2/get_token',
        code=authorization_code,
        client_secret=CLIENT_SECRET
    )
    
    print("[DEBUG] Received token:", json.dumps(token, indent=2))
    
    headers = {
        'Authorization': f'Bearer {token["access_token"]}',
        'Accept': 'application/json'
    }
    
    write_json_file('/tmp/access_token.json', headers)
    return headers

def read_json_file(filename):
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except FileNotFoundError as e:
        # print(f'[!] File not found: {e}')
        return None


def get_api_response(url, headers, params=None):
    response = requests.get(url, headers=headers, params=params)
    if response.status_code != 200:
        print(
            f'[!] API request failed with status code: {response.status_code}')
        return None
    return response.json()


def get_game_id(headers, github_api):

    file_path = "game_key.json"
    response = github_api.get_file_content(file_path)

    # If it exists parse json and return key
    if response == 200:
        return response["game_key"]

    api_url = f'{BASE_URL}/game/nfl'
    response_data = get_api_response(
        api_url, headers, params={'format': 'json'})

    if response_data:
        game_key = response_data["fantasy_content"]["game"][0]["game_id"]
        print(f'[+] Retrieved game_key: {game_key}')
        new_content = {"game_key": game_key}
        github_api.post_file_content(
            file_path, new_content, "Update game_key.")
        return game_key

    print('[*] Getting new token with get_new_oauth_token() -> main().')
    get_new_oauth_token()
    main()


def matchup_results(headers, week_number, github_api):
    weeks_to_process = range(1, 14) if week_number == 'a' else [int(week_number)]

    for week in weeks_to_process:
        file_path = f'week_{week}_matchup.json'
        response = github_api.get_file_content(file_path)

        process_current_week = True
        if response != 404:
            answer = input(f"[?] Week {week} already on git, process again (Y/n)?: ")
            process_current_week = answer.lower() != 'n'

        if not process_current_week:
            continue

        print(f"\n{'-' * 40} Week {week} {'-' * 40}")
        matchup_results = []

        # Get team data and handle potential 404
        team_data = github_api.get_file_content('teams_info.json')
        if isinstance(team_data, int):
            print("[!] Error: Could not retrieve teams_info.json")
            return

        for team in team_data:
            team_key = team["team_key"]
            team_name = team["team_name"]

            url = f'{BASE_URL}/team/{team_key}/matchups'
            response = requests.get(url, headers=headers, params={'format': 'json'})
            
            try:
                json_data = response.json()
                if response.status_code != 200:
                    print(f"[!] API request failed with status code: {response.status_code}")
                    print(json.dumps(json_data, indent=2))
                    continue

                post_event = json_data["fantasy_content"]["team"][1]["matchups"][str(int(week)-1)]["matchup"]["status"]
                
                if post_event != 'postevent':
                    print(f"[!] Week {week} is not over yet. Status: {post_event}")
                    break

                team_points = json_data["fantasy_content"]["team"][1]["matchups"][str(int(week)-1)]["matchup"]["0"]["teams"]["0"]["team"][1]["team_points"]["total"]
                opponent_points = json_data["fantasy_content"]["team"][1]["matchups"][str(int(week)-1)]["matchup"]["0"]["teams"]["1"]["team"][1]["team_points"]["total"]
                opponent_name = json_data["fantasy_content"]["team"][1]["matchups"][str(int(week)-1)]["matchup"]["0"]["teams"]["1"]["team"][0][2]["name"]
                opponent_team_key = json_data["fantasy_content"]["team"][1]["matchups"][str(int(week)-1)]["matchup"]["0"]["teams"]["1"]["team"][0][0]["team_key"]

                team_exists = any(matchup['team_name'] == team_name or matchup['opponent_name'] == team_name for matchup in matchup_results)
                opponent_exists = any(matchup['team_name'] == opponent_name or matchup['opponent_name'] == opponent_name for matchup in matchup_results)

                if not team_exists and not opponent_exists:
                    if float(team_points) > float(opponent_points):
                        difference = float(team_points) - float(opponent_points)
                        margin = str(round(difference, 2))
                        print(f"\033[32m{team_name} {team_points}\033[0m vs {opponent_name} {opponent_points}\n---> {team_name} wins by: {margin}\n")
                        winning_team = team_name
                    elif float(opponent_points) > float(team_points):
                        difference = float(opponent_points) - float(team_points)
                        margin = str(round(difference, 2))
                        print(f"\033[32m{opponent_name} {opponent_points}\033[0m vs {team_name} {team_points}\n---> {opponent_name} wins by: {margin}\n")
                        winning_team = opponent_name
                    else:
                        print(f"\033[31m{team_name} {team_points} vs {opponent_name} {opponent_points}\033[0m\n")
                        margin = "tie"
                        winning_team = "tie"

                    matchup = {
                        "team_key": team_key,
                        "team_name": team_name,
                        "week": str(week),
                        "team_points": team_points,
                        "opponent_points": opponent_points,
                        "opponent_name": opponent_name,
                        "opponent_team_key": opponent_team_key,
                        "margin_victory": margin,
                        "winning_team": winning_team
                    }

                    matchup_results.append(matchup)

            except KeyError as e:
                print(f"[!] KeyError for team {team_name}: {str(e)}")
                print(json.dumps(json_data, indent=2))
                continue
            except Exception as e:
                print(f"[!] Unexpected error for team {team_name}: {str(e)}")
                continue

        if matchup_results:
            file_path = f'week_{week}_matchup.json'
            github_api.post_file_content(file_path, matchup_results, "Update matchup results.")

def survivor_bonus_gather_data(github_api):

    weeks = list(range(1, 14))
    all_weeks_data = []

    for week_number in weeks:
        # Open the week_{}_matchup.json file for the specified week
        week_matchup_file = f'week_{week_number}_matchup.json'
        matchup_results = github_api.get_file_content(week_matchup_file)

        # Check if matchup_results is an integer (possibly a HTTP status code)
        if isinstance(matchup_results, int):
            print(
                f"[!] Week {week_number} data could not be loaded. Status code: {matchup_results}")
            continue  # Skip to the next iteration of the loop

        else:
            all_weeks_data.append(matchup_results)
    
    return all_weeks_data


def survivor_bonus_process_season(weekly_data, github_api):
    print_function_name('Survivor Results')

    teams_info = github_api.get_file_content('teams_info.json')

    # Initialize a set with all team keys at the start of the season
    active_teams = {team['team_key'] for team in teams_info}

    # Process each week
    for week in weekly_data:
        #print(f"\n[Debug] Week {week[0]['week']} - Active teams before elimination: {len(active_teams)}")

        # Collect scores for all active teams
        team_scores = {}
        for matchup in week:
            if matchup['team_key'] in active_teams:
                team_scores[matchup['team_key']] = float(matchup['team_points'])
            if matchup['opponent_team_key'] in active_teams:
                team_scores[matchup['opponent_team_key']] = float(matchup['opponent_points'])

        # Debugging: Print team scores
        #print(f"[Debug] Week {week[0]['week']} team scores: {team_scores}")

        # Skip the week if no active teams remain
        if not team_scores:
            #print(f"[Debug] Week {week[0]['week']} - No active teams to process.")
            continue

        # Find the team with the lowest score for the week
        lowest_scoring_team = min(team_scores, key=team_scores.get)
        lowest_scoring_team_name = [team['team_name'] for team in teams_info if team['team_key'] == lowest_scoring_team][0]
        lowest_scoring_team_points = team_scores[lowest_scoring_team]

        # Eliminate the lowest scoring team from the active teams
        active_teams.remove(lowest_scoring_team)
        print(f"[*] Survivor bonus week {week[0]['week']} eliminated {lowest_scoring_team_name} with {lowest_scoring_team_points} points.")
        #print(f'Remaining teams: {active_teams}')

        # Check if we have a winner
        if len(active_teams) == 1:
            team_key_to_name = {team['team_key']: team['team_name'] for team in teams_info}
            winner_key = next(iter(active_teams))
            winner_name = team_key_to_name.get(winner_key, "Unknown Team")
            print(f"[+] Survivor bonus winner: {winner_name}!")
            break

def get_team_info(game_id, headers, github_api):
    LEAGUE_ID = "410864"  # Ulster Nation XIV
    teams_info = []
    print("[+] Pulling individual team key values for Ulster Nation XIV")
    
    for team_index in range(1, 13):
        team_key = f'{game_id}.l.{LEAGUE_ID}.t.{team_index}'
        print(f"[*] Found team key: {team_key}")
        url = f'{BASE_URL}/team/{team_key}/matchups'
        response = requests.get(url, headers=headers, params={'format': 'json'})
        
        try:
            json_data = response.json()
            if response.status_code != 200:
                print(f"[!] API request failed with status code: {response.status_code}")
                print("[*] Response content:")
                print(json.dumps(json_data, indent=2))
                continue

            team_data = json_data["fantasy_content"]["team"][0]
            team_key = team_data[0]["team_key"]
            team_id = team_data[1]["team_id"]
            team_name = team_data[2]["name"]

            team_info = {
                "team_key": team_key,
                "team_id": team_id,
                "team_name": team_name
            }

            teams_info.append(team_info)
            print(f"[+] Successfully added {team_name}")

        except Exception as e:
            print(f"[!] Error processing team {team_index}: {str(e)}")
            continue

    if teams_info:
        github_api.post_file_content('teams_info.json', teams_info, "Update team ids and names.")
        return teams_info
    return None

def calculate_skins_winners(github_api):
    print_function_name(' Skins Results ')
    # If in DEBUG mode, print the function name for diagnostics.

    # Fetch the content of the 'skins_winners.json' file.
    skins_winners = github_api.get_file_content('skins_winners.json')

    # If the file does not exist, initialize an empty dictionary.
    if skins_winners == 404:
        print("[*] 404 getting skins_winners.json. Created empty dict.")
        skins_winners = {}

    # Initialize the pot for skins winner.
    current_pot = 10  # Initial pot value

    # Iterate through the JSON files for each week's matchup.
    for week_number in range(1, 18):
        week_file = f"./week_{week_number}_matchup.json"
        matchup_results = github_api.get_file_content(week_file)

        # Skip the week if matchup data isn't available.
        if matchup_results == 404:
            continue

        # Dictionary to track potential winners for the week.
        potential_winners = {}

        # Evaluate each matchup for the week.
        for matchup in matchup_results:
            winning_team = matchup['winning_team']
            margin_victory = float(matchup['margin_victory'])

            # Skip teams with victory margins less than 20.
            if margin_victory < 20:
                continue

            # Update the potential winners based on margin of victory.
            if winning_team in potential_winners:
                if margin_victory > potential_winners[winning_team]['margin_victory']:
                    potential_winners[winning_team]['margin_victory'] = margin_victory
            else:
                potential_winners[winning_team] = {
                    'margin_victory': margin_victory, 'week_number': week_number}

        # Skip the rest if there are no potential winners.
        if not potential_winners:
            current_pot += 10  # Increase the pot if there's no winner
            continue

        # Find the team with the highest margin of victory for the week.
        winning_team = max(
            potential_winners, key=lambda team: potential_winners[team]['margin_victory'])
        winning_margin = potential_winners[winning_team]['margin_victory']

        # Initialize or update the team's data in the skins_winners dictionary.
        if winning_team not in skins_winners:
            skins_winners[winning_team] = {'margin_victory': 0}

        skins_winners[winning_team]['margin_victory'] = winning_margin
        skins_winners[winning_team]['week_number'] = week_number

        # Assign the current pot to the winning team and reset the pot.
        skins_winners[winning_team]['pot_winnings'] = current_pot
        current_pot = 10  # Reset the pot value

        # Display the winner for the week.
        print(
            f"[*] Skins winner for week {week_number} {winning_team} by {round(winning_margin, 2)}")

    # Post the updated winners data back to GitHub.
    github_api.post_file_content(
        'skins_winners.json', skins_winners, "Update skins_winners.json")


def write_json_file(filename, data):
    with open(filename, 'w') as f:
        json.dump(data, f, indent=4)


def print_function_name(myfunction):
    header_line = "*"*40+myfunction+"*"*40
    print(header_line)


def main():
    # Github settings
    owner = 'cd1zz'
    repo = 'ffbstorage'

    try:
        token = os.environ['GITHUB_TOKEN']
    except KeyError:
        raise EnvironmentError("[!] GITHUB_TOKEN environment variable not set")

    github_api = GitHubAPI(owner, repo, token)
    
    headers = read_json_file('/tmp/access_token.json')
    if headers is None:
        headers = get_new_oauth_token()
    
    # Verify league access before proceeding
    if not verify_league_access(headers):
        print("[!] Unable to access league. Please verify:")
        print("1. OAuth scope includes 'fspt-r'")
        print("2. Access token is valid")
        print("3. User has access to league 254783")
        return

    # Get the game ID and team info
    game_id = get_game_id(headers, github_api)
    response = github_api.get_file_content("teams_info.json")
    if response == 404:
        print("[*] 404 getting teams_info.json. Retrieving...")
        get_team_info(game_id, headers, github_api)

    # Week input handling
    while True:
        user_input = input("[?] Enter week # or 'a' for all (weeks 1-13): ")
        try:
            week = int(user_input)
            if 1 <= week <= 13:
                break
            print('[!] Error. Weeks should be 1 - 17 only.')
        except ValueError:
            if user_input.lower() == 'a':
                week = 'a'
                break
            print('[!] Error. Enter valid week number or "a" for all.')

    # Process data
    week = str(week)
    matchup_results(headers, week, github_api)
    calculate_skins_winners(github_api)
    all_matchup_data = survivor_bonus_gather_data(github_api)
    survivor_bonus_process_season(all_matchup_data, github_api)
    print("[*] Complete!")
if __name__ == "__main__":
    main()
