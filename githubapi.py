import requests
import json
import base64

class GitHubAPI:
    BASE_URL = 'https://api.github.com'

    def __init__(self, owner, repo, token):
        self.owner = owner
        self.repo = repo
        self.headers = {
            'Authorization': f'token {token}'
        }

    def _make_request(self, method, path, data=None):
        """Helper method to make API requests."""
        url = f'{self.BASE_URL}{path}'
        if method == "GET":
            response = requests.get(url, headers=self.headers)
        elif method == "PUT":
            response = requests.put(url, headers=self.headers, json=data)
        
        if response.status_code in [200, 201]:
            return response.json()
        
        if response.status_code == 404:
            return response.status_code
        else:
            response.raise_for_status()

    def get_file_content(self, file_path):
        """Fetch the content of a file from the repository."""
        path = f'/repos/{self.owner}/{self.repo}/contents/{file_path}'
        file_data = self._make_request("GET", path)
        
        if file_data == 404:
            return file_data
        
        # Decoding the content from base64
        decoded_content = base64.b64decode(file_data['content']).decode('utf-8')
        return json.loads(decoded_content)

    def post_file_content(self, file_path, content, commit_message):
        """Post new content to a file in the repository."""
        path = f'/repos/{self.owner}/{self.repo}/contents/{file_path}'

        # Encoding the content to base64
        encoded_content = base64.b64encode(json.dumps(content).encode('utf-8')).decode('utf-8')

        data = {
            "message": commit_message,
            "content": encoded_content
        }

        # If the file already exists, we need to include the SHA of the file to update it
        try:
            existing_file_data = self._make_request("GET", path)
            data["sha"] = existing_file_data["sha"]
        except requests.HTTPError as e:
            if e.response.status_code != 404:
                raise  # re-raise the exception if it's not a "Not Found" error
        except TypeError as e:
            # If file doesnt exist, there wont be a SHA
            pass

        return self._make_request("PUT", path, data)