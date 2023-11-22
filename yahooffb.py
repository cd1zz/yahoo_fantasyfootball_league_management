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


def get_new_oath_token():

    # Create an OAuth2Session
    yahoo = OAuth2Session(CLIENT_ID, redirect_uri=REDIRECT_URI, scope=SCOPE)

    # Generate the authorization URL with the scope parameter
    authorization_url, state = yahoo.authorization_url(
        'https://api.login.yahoo.com/oauth2/request_auth')

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

    headers = {'Authorization': f'Bearer {token["access_token"]}',  # Include the access token in the Authorization header
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

    print('[*] Getting new token with get_new_oath_token() -> main().')
    get_new_oath_token()
    main()


def matchup_results(headers, week_number, github_api):

    weeks_to_process = range(1, 14) if week_number == 'a' else [
        int(week_number)]

    for week in weeks_to_process:
        # Check if we already did this
        file_path = f'week_{week}_matchup.json'
        response = github_api.get_file_content(file_path)

        process_current_week = True  # Flag to indicate whether to process the current week

        if response == 404:
            answer = 'y'
            pass
        else:
            while True:  # Keep looping until a valid answer is given
                answer = input(
                    f"[?] Week {week} already on git, process again (Y/n)?: ")

                if 'n' in answer.lower():
                    process_current_week = False  # Set flag to false if user enters 'n'
                    break  # Exit the while loop
                elif 'y' in answer.lower() or not answer:  # Check for 'y' or empty input
                    answer = 'y'
                    break  # This will exit the while loop and continue with the rest of the code
                else:
                    print("[!] Enter y or n, or simply press enter for 'yes'.")

        if not process_current_week:
            continue

        print(f"\n{'-' * 40} Week {week} {'-' * 40}")

        matchup_results = []

        team_data = github_api.get_file_content('teams_info.json')

        for idx, team in enumerate(team_data, start=1):
            team_key = team["team_key"]
            team_name = team["team_name"]

            url = f'{BASE_URL}/team/{team_key}/matchups'
            response = requests.get(
                url, headers=headers, params={'format': 'json'})
            try:
                post_event = response.json()["fantasy_content"]["team"][1]["matchups"][str(
                    int(week)-1)]["matchup"]["status"]
            except KeyError:
                print(json.dumps(response.json(), indent=4))
                raise KeyError(f"[!] KeyError for json.")

            if post_event != 'postevent':
                print(
                    f"[!] Week {week} is not over yet. Exiting loop. Status: {post_event}")
                answer = 'n'
                break

            team_points = response.json()["fantasy_content"]["team"][1]["matchups"][str(
                int(week)-1)]["matchup"]["0"]["teams"]["0"]["team"][1]["team_points"]["total"]
            opponent_points = response.json()["fantasy_content"]["team"][1]["matchups"][str(
                int(week)-1)]["matchup"]["0"]["teams"]["1"]["team"][1]["team_points"]["total"]
            opponent_name = response.json()["fantasy_content"]["team"][1]["matchups"][str(
                int(week)-1)]["matchup"]["0"]["teams"]["1"]["team"][0][2]["name"]

            team_exists = any(matchup['team_name'] == team_name or matchup['opponent_name']
                              == team_name for matchup in matchup_results)
            opponent_exists = any(
                matchup['team_name'] == opponent_name or matchup['opponent_name'] == opponent_name for matchup in matchup_results)

            if not team_exists and not opponent_exists:
                if float(team_points) > float(opponent_points):
                    difference = float(team_points) - float(opponent_points)
                    margin = str(round(difference, 2))
                    print(
                        f"\033[32m{team_name} {team_points}\033[0m vs {opponent_name} {opponent_points}\n---> {team_name} wins by: {margin}\n")
                    winning_team = team_name
                elif float(opponent_points) > float(team_points):
                    difference = float(opponent_points) - float(team_points)
                    margin = str(round(difference, 2))
                    print(
                        f"\033[32m{opponent_name} {opponent_points}\033[0m vs {team_name} {team_points}\n---> {opponent_name} wins by: {margin}\n")
                    winning_team = opponent_name
                else:
                    print(
                        f"\033[31m{team_name} {team_points} vs {opponent_name} {opponent_points}\033[0m\n")
                    margin = "tie"
                    winning_team = "tie"

                matchup = {
                    "team_key": team_key,
                    "team_name": team_name,
                    "week": str(week),
                    "team_points": team_points,
                    "opponent_points": opponent_points,
                    "opponent_name": opponent_name,
                    "margin_victory": margin,
                    "winning_team": winning_team
                }

                matchup_results.append(matchup)

        if 'y' in answer.lower():
            file_path = f'week_{week}_matchup.json'
            github_api.post_file_content(
                file_path, matchup_results, "Update matchup results.")


def load_eliminated_teams(github_api):

    survivor_results = github_api.get_file_content('survivor_bonus.json')

    if survivor_results == 404:
        print("[*] 404 on survivor_bonus.json. Creating empty set().")
        time.sleep(5)
        return set()
    else:
        losing_team_names = set()
        # Parse the JSON string

        for team in survivor_results:
            losing_team_names.add(team['losing_team_name'])

        return losing_team_names


def survivor_bonus(week_number, github_api):

    response = github_api.get_file_content('survivor_bonus.json')

    if response == 404:
        survivor_bonus_data = []

    else:
        survivor_bonus_data = response

    # Load the eliminated teams from the file
    eliminated_teams = load_eliminated_teams(github_api)

    if week_number == 'a':
        weeks = list(range(1, 14))

    else:
        weeks = [week_number]

    for week_number in weeks:
        # Open the week_{}_matchup.json file for the specified week
        week_matchup_file = f'week_{week_number}_matchup.json'
        matchup_results = github_api.get_file_content(week_matchup_file)

        # Check if matchup_results is an integer (possibly a HTTP status code)
        if isinstance(matchup_results, int):
            print(
                f"[!] Week {week_number} data could not be loaded. Status code: {matchup_results}")
            continue  # Skip to the next iteration of the loop

        # Find the lowest points among all teams
        lowest_points = float('inf')  # Initialize with a very high value

        for matchup in matchup_results:

            week_exists = any(item["week_eliminated"] ==
                              week_number for item in survivor_bonus_data)

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
        lowest_teams = [matchup['team_name'] for matchup in matchup_results if float(
            matchup['team_points']) == lowest_points]

        for lowest_team in lowest_teams:
            # Check if the losing team is already in survivor_bonus_data
            losing_team_exists = any(
                item['losing_team_name'] == lowest_team for item in survivor_bonus_data)

            if not losing_team_exists:
                # Create a dictionary for the team with the lowest points
                lowest_team_info = {
                    "losing_team_name": lowest_team,
                    "lowest_points": lowest_points,
                    "week_eliminated": int(week_number)
                }

                survivor_bonus_data.append(lowest_team_info)

                # Add the eliminated team to the set and save it
                eliminated_teams.add(lowest_team)

    github_api.post_file_content(
        'survivor_bonus.json', survivor_bonus_data, "Update survivor_bonus.json")

    if lowest_points > 10000:
        print(f"[!] No teams eliminated from survivor pool.")


def get_team_info(game_id, headers, github_api):
    teams_info = []
    print("[+] Pulling individual team key values.")
    for team_index in range(1, 13):
        team_key = f'{game_id}.l.254783.t.{team_index}'
        print(f"[*] Found team key: {team_key}")
        url = f'{BASE_URL}/team/{team_key}/matchups'
        response = requests.get(url, headers=headers,
                                params={'format': 'json'})
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

    github_api.post_file_content(
        'teams_info.json', teams_info, "Update team ids and names.")

    return


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


def print_survior_teams_eliminated(github_api):

    print_function_name(' Survivor Results ')
    eliminated_teams = github_api.get_file_content('survivor_bonus.json')
    if eliminated_teams == 404:
        print("[*] 404 getting surivor_bonus.json. Sleeping 5 seconds.")
        time.sleep(5)
        eliminated_teams = github_api.get_file_content('survivor_bonus.json')

    for team in eliminated_teams:
        print(
            f"[*] Surivor bonus team eliminated for week {team['week_eliminated']} {team['losing_team_name']} with {team['lowest_points']}."
        )
    # JSON data for the first file (teams)
    teams_data = github_api.get_file_content('teams_info.json')

    # Extract team names from both datasets
    team_names = set(team["team_name"] for team in teams_data)
    eliminated_team_names = set(team["losing_team_name"]
                                for team in eliminated_teams)

    # Find teams in the first file but not in the second
    teams_not_eliminated = team_names - eliminated_team_names

    # Print the result
    print("[*] Survivor teams still alive:", teams_not_eliminated)


def main():

    # Github settings to post json files to ffbstorage for centralized data storage
    owner = 'cd1zz'
    repo = 'ffbstorage'

    try:
        token = os.environ['GITHUB_TOKEN']
    except KeyError:
        raise EnvironmentError(
            "[!] The environment variable GITHUB_TOKEN is not set. This is the personal access token from github.")

    github_api = GitHubAPI(owner, repo, token)

    headers = read_json_file('/tmp/access_token.json')
    if headers is None:
        headers = get_new_oath_token()

    # Get the game ID
    game_id = get_game_id(headers, github_api)

    response = github_api.get_file_content("teams_info.json")
    if response == 404:
        print("[*] 404 getting teams_info.json. Retrieving...")
        get_team_info(game_id, headers, github_api)

    # Ask the user for the week number
    while True:  # This loop will keep asking until a valid input is given
        user_input = input(
            "[?] Enter the week # or 'a' for all (weeks 1-13): ")
        try:
            week = int(user_input)  # This line can throw a ValueError
            if 1 <= week <= 13:
                break  # Exit the loop if the input is valid
            else:
                print('[!] Error. Weeks should be 1 - 17 only.')
        except ValueError:
            if user_input.lower() == 'a':  # Allow 'a' or 'A' for all weeks
                week = 'a'
                break
            else:
                print(
                    '[!] Error. Please enter a valid integer for the week number or \'a\' for all.')

    week = str(week)
    matchup_results(headers, week, github_api)
    survivor_bonus(week, github_api)
    print_survior_teams_eliminated(github_api)
    calculate_skins_winners(github_api)
    print("[*] Complete!")


if __name__ == "__main__":
    main()
