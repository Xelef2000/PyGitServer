import http.server
import socketserver
import subprocess
import os
import yaml
import shutil
from urllib.parse import urlparse, parse_qs
import re
import gzip

# --- Load Configuration ---
# Determine config file path from environment variable or use default
config_path = os.getenv('GIT_SERVER_CFG', 'config.yaml')
print(f"Attempting to load configuration from: {config_path}")

try:
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    HOST = config['server']['host']
    PORT = config['server']['port']
    REPOS_CONFIG = config['repositories']
    # Create a mapping from repo name to repo path for quick lookups
    REPO_MAP = {repo['name']: repo['path'] for repo in REPOS_CONFIG}
except FileNotFoundError:
    print(f"Error: Configuration file not found at '{config_path}'.")
    print("Please create the file or set the GIT_SERVER_CFG environment variable to its location.")
    exit(1)
except (KeyError, TypeError) as e:
    print(f"Error: Invalid format in config file '{config_path}'. Ensure 'server' and 'repositories' keys are set correctly. Details: {e}")
    exit(1)

# --- Setup Functions ---
def check_git_installed():
    """Checks if the 'git' command is available in the system's PATH."""
    if not shutil.which("git"):
        print("Error: Git could not be found.")
        print("Please install Git and ensure it is in your system's PATH to continue.")
        return False
    print("Git installation found.")
    return True

def setup_repositories(repos):
    """Checks and creates all configured repositories."""
    print("\n--- Initializing Repositories ---")
    for repo_config in repos:
        repo_name = repo_config['name']
        repo_path = repo_config['path']
        init_from = repo_config.get('init_from')  # Get the optional init_from URL

        print(f"Checking for '{repo_name}' at '{repo_path}'...")
        if os.path.isdir(repo_path):
            print(f"-> Repository '{repo_name}' already exists.")
            continue

        # Ensure parent directory exists
        parent_dir = os.path.dirname(repo_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
            
        try:
            command = []
            if init_from:
                print(f"-> Repository not found. Cloning from '{init_from}'...")
                command = ['git', 'clone', '--bare', init_from, repo_path]
            else:
                print(f"-> Repository not found. Creating new empty bare repository...")
                command = ['git', 'init', '--bare', repo_path]

            result = subprocess.run(
                command, check=True, capture_output=True, text=True
            )
            # Git clone often prints progress to stderr, so we show it if available.
            output = result.stdout.strip() or result.stderr.strip()
            print(f"-> {output}")
            print(f"-> Repository '{repo_name}' setup successfully.")

        except subprocess.CalledProcessError as e:
            print(f"!! Failed to set up repository '{repo_name}'. Git command failed:")
            print(e.stderr)
            return False
        except Exception as e:
            print(f"!! An unexpected error occurred while setting up '{repo_name}': {e}")
            return False
            
    print("--- Repository setup complete ---\n")
    return True

# --- Git Server Logic ---
class GitHTTPRequestHandler(http.server.BaseHTTPRequestHandler):
    """
    A request handler that serves multiple Git repositories over HTTP.
    """
    def get_repo_path(self):
        """Parses the request URL to find the repo name and get its disk path."""
        # The first part of the path is the repo name. e.g., /my-repo/info/refs
        match = re.match(r'^/([^/]+)', self.path)
        if not match:
            return None, "Invalid repository URL."

        repo_name = match.group(1)
        repo_path = REPO_MAP.get(repo_name)
        
        if not repo_path or not os.path.isdir(repo_path):
            return None, f"Repository '{repo_name}' not found on server."
        
        return repo_path, None

    def _send_headers(self, status_code, content_type, extra_headers=None):
        """Send common headers for a Git HTTP response."""
        self.send_response(status_code)
        self.send_header('Content-Type', content_type)
        self.send_header('Expires', 'Fri, 01 Jan 1980 00:00:00 GMT')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Cache-Control', 'no-cache, max-age=0, must-revalidate')
        if extra_headers:
            for key, value in extra_headers.items():
                self.send_header(key, value)
        self.end_headers()

    def _execute_git_command(self, repo_path, service_name, command_options, input_data=None):
        """Executes a git command for a specific repository."""
        command = ['git', service_name.replace('git-', ''), '--stateless-rpc'] + command_options + [repo_path]
        
        try:
            proc = subprocess.Popen(
                command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            stdout, stderr = proc.communicate(input=input_data)

            if proc.returncode != 0:
                print(f"Git command error for '{' '.join(command)}':\n{stderr.decode('utf-8', errors='ignore')}")
                self.send_error(500, "Git command failed on server.")
                return None
            return stdout
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            self.send_error(500, "Internal Server Error.")
            return None

    def process_request(self, service_name_suffix):
        """Generic handler for both GET and POST."""
        repo_path, error = self.get_repo_path()
        if error:
            self.send_error(404, error)
            return

        parsed_path = urlparse(self.path)
        
        if self.command == 'GET':
            query_params = parse_qs(parsed_path.query)
            service = query_params.get('service', [None])[0]
            if not service or not parsed_path.path.endswith('/info/refs'):
                self.send_error(404, "Not Found")
                return

            content_type = f'application/x-{service}-advertisement'
            self._send_headers(200, content_type)
            header = f'# service={service}\n'
            encoded_header = f'{len(header) + 4:04x}{header}0000'
            self.wfile.write(encoded_header.encode('utf-8'))
            output = self._execute_git_command(repo_path, service, ['--advertise-refs'])
            if output:
                self.wfile.write(output)
        
        elif self.command == 'POST':
            service_name = os.path.basename(parsed_path.path)
            if service_name != service_name_suffix:
                 self.send_error(400, "Service mismatch in URL.")
                 return

            content_length = int(self.headers.get('Content-Length', 0))
            input_data = self.rfile.read(content_length)

            # Decompress request body if client sent it gzipped
            if self.headers.get('Content-Encoding') == 'gzip':
                try:
                    input_data = gzip.decompress(input_data)
                except (gzip.BadGzipFile, EOFError):
                    self.send_error(400, "Bad gzipped data in request")
                    return

            output = self._execute_git_command(repo_path, service_name, [], input_data=input_data)
            
            if output is None:
                # _execute_git_command already sent an error
                return

            # Now, prepare the response
            extra_headers = {}
            # Check if the output from git is gzipped and add header if so
            if output.startswith(b'\x1f\x8b'):
                extra_headers['Content-Encoding'] = 'gzip'

            content_type = f'application/x-{service_name}-result'
            self._send_headers(200, content_type, extra_headers)
            
            self.wfile.write(output)

    def do_GET(self):
        self.process_request(None)

    def do_POST(self):
        service_name = os.path.basename(urlparse(self.path).path)
        if service_name not in ('git-upload-pack', 'git-receive-pack'):
            self.send_error(404, "Service not found.")
            return
        self.process_request(service_name)

# --- Main Server Execution ---
if __name__ == "__main__":
    if not check_git_installed():
        exit(1)

    if not setup_repositories(REPOS_CONFIG):
        print("Server cannot start due to repository setup failure.")
        exit(1)

    with socketserver.TCPServer((HOST, PORT), GitHTTPRequestHandler) as server:
        print(f"Serving {len(REPO_MAP)} Git repositories on http://{HOST}:{PORT}")
        for name in REPO_MAP:
            print(f" -> http://{HOST}:{PORT}/{name}")
        print("\nServer is running. Press Ctrl+C to shut down.")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nServer shutting down.")
            server.shutdown()

