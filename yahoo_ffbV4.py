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
CLIENT_ID = 'dj0yJmk9M2ZVMmZWVzkyQVdoJmQ9WVdrOU5rdzJObkV6VVZNbWNHbzlNQT09JnM9Y29uc3VtZXJzZWNyZXQmc3Y9MCZ4PWQ5' #AKA Consumer Key
CLIENT_SECRET = '5811fc285d6da54cd9b07e5bec1d9a39b4e80128' #AKA Consumer Secret'
REDIRECT_URI = 'oob'
SCOPE = 'fspt-r'
DEBUG = False

def get_new_oath_token():
    if DEBUG:
        print_function_name(inspect.currentframe().f_code.co_name)
    
    # Create an OAuth2Session
    yahoo = OAuth2Session(CLIENT_ID, redirect_uri=REDIRECT_URI, scope=SCOPE)

    # Generate the authorization URL with the scope parameter
    authorization_url, state = yahoo.authorization_url('https://api.login.yahoo.com/oauth2/request_auth')

    print('[*] Please go to the following URL and authorize your application:')
    print(authorization_url)

    # After the user authorizes your application, they will be presented with an authorization code that they can manually enter into your script.
    authorization_code = input('[?] Enter the authorization code: ')

    # Fetch the access token using the authorization code
    token = yahoo.fetch_token(
        'https://api.login.yahoo.com/oauth2/get_token',
        code=authorization_code,  # Pass the authorization code here
        client_secret=CLIENT_SECRET
    )

    # Close the session when done
    yahoo.close()

    headers = {
        'Authorization': f'Bearer {token["access_token"]}',  # Include the access token in the Authorization header
    }
    
    with open('access_token.json', 'w') as f:
        json.dump(headers, f)
    
    return headers

def read_json_file(filename):
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except FileNotFoundError as e:
        #print(f'[!] File not found: {e}')
        return None
    
def get_api_response(url, headers, params=None):
    response = requests.get(url, headers=headers, params=params)
    if response.status_code != 200:
        print(f'[!] API request failed with status code: {response.status_code}')
        return None
    return response.json()

def get_game_id(headers,github_api):
    if DEBUG:
        print_function_name()
    file_path = "game_key.json"
    response = github_api.get_file_content(file_path)

    # If it exists parse json and return key
    if response == 200:
        return response["game_key"]

    api_url = f'{BASE_URL}/game/nfl'
    response_data = get_api_response(api_url, headers, params={'format': 'json'})

    if response_data:
        game_key = response_data["fantasy_content"]["game"][0]["game_id"]
        print(f'[+] Retrieved game_key: {game_key}')
        new_content = {"game_key":game_key}
        github_api.post_file_content(file_path, new_content, "Update game_key.")
        return game_key

    print('[*] Getting new token with get_new_oath_token() -> main().')
    get_new_oath_token()
    main()

def matchup_results(game_id, headers, week_number, github_api):
    print(f"\n{'-' * 40} Week {week_number} {'-' * 40}")

    matchup_results = []

    team_data = github_api.get_file_content('teams_info.json')
    #team_data = read_json_file('teams_info.json')

    for idx, team in enumerate(team_data, start=1):
        team_key = team["team_key"]
        team_name = team["team_name"]

        url = f'https://fantasysports.yahooapis.com/fantasy/v2/team/{team_key}/matchups'
        response = requests.get(url, headers=headers, params={'format': 'json'})
        post_event = response.json()["fantasy_content"]["team"][1]["matchups"][str(int(week_number)-1)]["matchup"]["status"]

        if post_event != 'postevent':
            print(f"[!] Week {week_number} is not over yet. Exiting loop. Status: {post_event}")
            break

        team_points = response.json()["fantasy_content"]["team"][1]["matchups"][str(int(week_number)-1)]["matchup"]["0"]["teams"]["0"]["team"][1]["team_points"]["total"]
        opponent_points = response.json()["fantasy_content"]["team"][1]["matchups"][str(int(week_number)-1)]["matchup"]["0"]["teams"]["1"]["team"][1]["team_points"]["total"]
        opponent_name = response.json()["fantasy_content"]["team"][1]["matchups"][str(int(week_number)-1)]["matchup"]["0"]["teams"]["1"]["team"][0][2]["name"]

        team_exists = any(matchup['team_name'] == team_name or matchup['opponent_name'] == team_name for matchup in matchup_results)
        opponent_exists = any(matchup['team_name'] == opponent_name or matchup['opponent_name'] == opponent_name for matchup in matchup_results)

        if not team_exists and not opponent_exists:
            if float(team_points) > float(opponent_points):
                difference = float(team_points) - float(opponent_points)
                margin = str(difference)
                print(f"\033[32m{team_name} {team_points}\033[0m vs {opponent_name} {opponent_points}\n---> {team_name} wins by: {margin}\n")
                winning_team = team_name
            elif float(opponent_points) > float(team_points):
                difference = float(opponent_points) - float(team_points)
                margin = str(difference)
                print(f"\033[32m{opponent_name} {opponent_points}\033[0m vs {team_name} {team_points}\n---> {opponent_name} wins by: {margin}\n")
                winning_team = opponent_name
            else:
                print(f"\033[31m{team_name} {team_points} vs {opponent_name} {opponent_points}\033[0m\n")
                margin = "tie"
                winning_team = "tie"

            matchup = {
                "team_key": team_key,
                "team_name": team_name,
                "week": week_number,
                "team_points": team_points,
                "opponent_points": opponent_points,
                "opponent_name": opponent_name,
                "margin_victory": margin,
                "winning_team": winning_team
            }

            matchup_results.append(matchup)

    file_path = f'week_{week_number}_matchup.json'
    github_api.post_file_content(file_path, matchup_results, "Update matchup results.")
    #write_json_file(outfile, matchup_results)

def load_eliminated_teams(github_api):
    if DEBUG:
        print_function_name(inspect.currentframe().f_code.co_name)

    response = github_api.get_file_content('eliminated_teams.json')

    if response == 404:
        print("[*] 404 on eliminated_teams.json. Creating empty set().")
        return set()
    else:
        # Parse the JSON string
        teams = json.loads(response)
        
        # Ensure teams is a list before converting to a set
        if isinstance(teams, list):
            return set(teams)
        else:
            print("[*] Unexpected data format in eliminated_teams.json.")
            return set()
        
def save_eliminated_teams(eliminated_teams):
    if DEBUG:
        print_function_name(inspect.currentframe().f_code.co_name)
    
    #with open('eliminated_teams.txt', 'w') as f:
    #    for team in eliminated_teams:
    #        f.write(team + '\n')


def survivor_bonus(week_number, github_api):
    if DEBUG:
        print_function_name(inspect.currentframe().f_code.co_name)
    
    response = github_api.get_file_content('survivor_bonus.json')

    if response == 404:
        survivor_bonus_data = None
    
    else:
        survivor_bonus_data = response

    #survivor_bonus_data = read_json_file('survivor_bonus.json')
    
    if survivor_bonus_data is None:
        survivor_bonus_data = []

    # Open the week_{}_matchup.json file for the specified week
    week_matchup_file = f'week_{week_number}_matchup.json'
    matchup_results = github_api.get_file_content(week_matchup_file)

    # Load the eliminated teams from the file
    eliminated_teams = load_eliminated_teams(github_api)

    # Find the lowest points among all teams
    lowest_points = float('inf')  # Initialize with a very high value

    for matchup in matchup_results:
        week_exists = any(item["week_eliminated"] == week_number for item in survivor_bonus_data)

        # Skip if we already have an entry
        if week_exists:
            continue
        else:
            pass

        team_name = matchup['team_name']
        team_points = float(matchup['team_points'])

        # Skip eliminated teams
        if team_name in eliminated_teams:
            continue

        if team_points < lowest_points:
            lowest_points = team_points

    # Identify all teams with the lowest points
    lowest_teams = [matchup['team_name'] for matchup in matchup_results if float(matchup['team_points']) == lowest_points]

    for lowest_team in lowest_teams:
        # Check if the losing team is already in survivor_bonus_data
        losing_team_exists = any(item['losing_team_name'] == lowest_team for item in survivor_bonus_data)

        if not losing_team_exists:
            # Create a dictionary for the team with the lowest points
            lowest_team_info = {
                "losing_team_name": lowest_team,
                "lowest_points": lowest_points,
                "week_eliminated": week_number
            }

            survivor_bonus_data.append(lowest_team_info)

            # Add the eliminated team to the set and save it
            eliminated_teams.add(lowest_team)

    #for value in eliminated_teams:
    #    print(value)

    #input()
    #save_eliminated_teams(eliminated_teams)
    # Convert the eliminated_teams set to a list, and then to json. 

    eliminated_teams_json = json.dumps(list(eliminated_teams))
    #print(eliminated_teams_json)
    #input()

    github_api.post_file_content('eliminated_teams.json', eliminated_teams_json, "Update eliminated survivor teams.")
    github_api.post_file_content('survivor_bonus.json', survivor_bonus_data, "Update survivor_bonus.json")

    if lowest_points > 10000:
        print(f"[!] No teams eliminated from survivor pool.")

    else:
        print(f"[*] The team(s) with the lowest points in Week {week_number} is/are: {', '.join(lowest_teams)} with {lowest_points} points.")

    

def get_team_info(game_id, headers, github_api):
    teams_info = []
    print("[+] Pulling individual team key values.")
    for team_index in range(1, 13):
        team_key = f'{game_id}.l.254783.t.{team_index}'
        print(f"[*] Found team key: {team_key}")
        url = f'https://fantasysports.yahooapis.com/fantasy/v2/team/{team_key}/matchups'
        response = requests.get(url, headers=headers, params={'format': 'json'})
        json_data = response.json()

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

    github_api.post_file_content('teams_info.json', teams_info, "Update team ids and names.")
    #write_json_file('teams_info.json', teams_info)
    return
    #return response.json()


def calculate_skins_winners(github_api):
    if DEBUG:
        print_function_name(inspect.currentframe().f_code.co_name)

    #skins_winners = read_json_file('skins_winners.json')
    skins_winners = github_api.get_file_content('skins_winners.json')

    if skins_winners == 404:
        print("[*] 404 getting skins_winners.json. Created empty dict.")
        skins_winners = {}

    current_pot = 0

    # Iterate through the JSON files in the specified directory
    for week_number in range(1, 18):
        week_file = f"./week_{week_number}_matchup.json"
        matchup_results = github_api.get_file_content(week_file)

        if matchup_results == 404:
            #print(f"[*] Skipping week {week_number}, no matchup data.")
            continue

        # Dictionary to track the potential winners for this week
        potential_winners = {}

        for matchup in matchup_results:
            winning_team = matchup['winning_team']
            margin_victory = float(matchup['margin_victory'])

            if margin_victory >= 20:
                if winning_team in potential_winners:
                    if margin_victory > potential_winners[winning_team]['margin_victory']:
                        # Update the margin of victory for the team
                        potential_winners[winning_team]['margin_victory'] = margin_victory
                else:
                    # Add the team to potential winners
                    potential_winners[winning_team] = {
                        'margin_victory': margin_victory,
                        'week_number': week_number
                    }

        if potential_winners:
            # Find the team with the largest margin of victory
            winning_team = max(potential_winners, key=lambda team: potential_winners[team]['margin_victory'])

            if winning_team in skins_winners:
                # Update the margin of victory and week number for the team
                skins_winners[winning_team]['margin_victory'] = potential_winners[winning_team]['margin_victory']
                skins_winners[winning_team]['week_number'] = week_number
            else:
                # Add the team to skins winners
                skins_winners[winning_team] = {
                    'margin_victory': potential_winners[winning_team]['margin_victory'],
                    'week_number': week_number
                }

            # Update the current pot for this week
            current_pot += 10
            skins_winners[winning_team]['pot_winnings'] = current_pot

            print(f"[*] Skins winner for week {week_number} {winning_team} by {potential_winners[winning_team]['margin_victory']}")



    # Write the updated skins_winners to the JSON file
    #write_json_file('skins_winners.json',skins_winners)

    github_api.post_file_content('skins_winners.json',skins_winners,"Update skins_winners.json")

def write_json_file(filename, data):
    with open(filename, 'w') as f:
        json.dump(data, f, indent=4)


def print_function_name(myfunction):
    header_line = "*"*40+myfunction+"*"*40
    print(header_line)

def print_survior_teams_eliminated(github_api):
    
    eliminated_teams = github_api.get_file_content('survivor_bonus.json')
    if eliminated_teams == 404:
        print("[*] 404 getting surivor_bonus.json. Sleeping 5 seconds.")
        time.sleep(5)
        eliminated_teams = github_api.get_file_content('survivor_bonus.json')
    
    for team in eliminated_teams:
        print(f"[*] Surivor bonus team eliminated for week {team['week_eliminated']} {team['losing_team_name']} with {team['lowest_points']}.")
    
def main():

    if DEBUG:
        print_function_name(inspect.currentframe().f_code.co_name)

    owner = 'cd1zz'
    repo = 'ffb'
    token = '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'
    
    github_api = GitHubAPI(owner, repo, token)

    headers = read_json_file('access_token.json')
    if headers is None:
        headers = get_new_oath_token()

    # Get the game ID
    game_id = get_game_id(headers,github_api)

    response = github_api.get_file_content("teams_info.json")
    if response == 404:
        print("[*] 404 getting teams_info.json. Retrieving...")
        get_team_info(game_id, headers, github_api)

    # If the teams_info file doesn't exist, fetch the data
    #if read_json_file("teams_info.json") is None:
    #    get_team_info(game_id, headers)

    # Ask the user for the week number
    while True:  # This loop will keep asking until a valid input is given
        try:
            week = int(input("[?] Enter the week #: "))  # This line can throw a ValueError
            if 1 <= week <= 17:
                break  # Exit the loop if the input is valid
            else:
                print('[!] Error. Weeks should be 1 - 17 only.')
        except ValueError:
            print('[!] Error. Please enter a valid integer for the week number.')

    week = str(week)
    matchup_results(game_id, headers, week, github_api)
    
    survivor_bonus(week,github_api)
    print_survior_teams_eliminated(github_api)
    calculate_skins_winners(github_api)
    print("[*] Complete!")
if __name__ == "__main__":
    main()




