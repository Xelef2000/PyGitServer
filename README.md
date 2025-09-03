# PyGitServer: A Simple Python HTTP Git Server

This project provides a bare-bones, multi-repository Git server that runs over HTTP. 
On its first run, it will automatically create the "bare" Git repositories for you based on your configuration.

**Disclaimer:** This server has no authentication or authorization. Anyone with network access to the server can clone and push to any repository. **Do not use this in an untrusted environment.**

## Features

- Serves **multiple** Git repositories.
- **Automatic repository creation** on first launch.
- Can initialize repos by **cloning a remote URL**.
- Handles `git clone`, `git fetch`, and `git push` over HTTP, including support for compressed (gzip) traffic.
- Configurable via a simple `config.yaml` file.
- Configuration file path can be specified via the `GIT_SERVER_CFG` environment variable.
- Pure Python with no external dependencies (besides Git itself).

## Prerequisites

- **Python 3.6+**
- **Git:** The git command-line tool must be in the system's `PATH`.

## 1. Configuration

The server is configured using a YAML file. By default, it looks for `config.yaml` in the same directory as `server.py`.

```yaml
# config.yaml
server:
  host: "0.0.0.0"   # Binds to all network interfaces. Use "127.0.0.1" for local access only.
  port: 8000        # The port the server will listen on.

# List of repositories to serve.
# 'name' is used in the URL (e.g., http://host/repo-name)
# 'path' is the location on the disk.
repositories:
  - name: "my-first-repo"
    path: "./repos/my-first-repo.git"
  - name: "another-project"
    path: "./repos/another-project.git"
```

### Using an Environment Variable for Configuration

You can specify a different path for the configuration file by setting the `GIT_SERVER_CFG` environment variable.

```bash
# Example: Run the server with a config file located at /etc/git-server/config.yaml
export GIT_SERVER_CFG="/etc/git-server/config.yaml"
python3 server.py
```

### Initializing from a Remote Repository

You can also initialize a repository by cloning it from an existing remote URL. This is useful for creating a mirror or a fork. To do this, add the optional `init_from` key to a repository's configuration.

The server will only perform this clone operation **once**, when it first creates the repository.

```yaml
# Example entry in your repositories list
repositories:
  - name: "project-mirror"
    path: "./repos/project-mirror.git"
    # This will clone the remote repo instead of creating an empty one
    init_from: "https://github.com/someuser/someproject.git"
```

## 2. Running the Server

Once the configuration is set, you can start the server:

```bash
python3 server.py
```

The server will read the repositories list and create any that do not exist. On subsequent runs, it will detect the existing repositories and use them.

If successful, you will see a message listing the available repositories:

```
Attempting to load configuration from: config.yaml
Git installation found.

--- Initializing Repositories ---
Checking for 'my-first-repo' at './repos/my-first-repo.git'...
-> Repository 'my-first-repo' already exists.
--- Repository setup complete ---

Serving 1 Git repositories on http://0.0.0.0:8000
 -> http://0.0.0.0:8000/my-first-repo

Server is running. Press Ctrl+C to shut down.
```


