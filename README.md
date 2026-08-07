# Running Pitchside locally

Browsers won't let a webpage load local files like `fpl_players.json` when
you just double-click `index.html` to open it — that's a security rule
called CORS. The fix is to serve the folder through a tiny local web server,
which Python can already do, no installs needed.

## Steps

1. Open PowerShell and navigate to this folder (you're probably already here):
   ```
   cd "C:\Users\rhyst\OneDrive\Desktop\fpl-website\player data"
   ```

2. Start a local server:
   ```
   python -m http.server 8000
   ```
   You'll see something like `Serving HTTP on :: port 8000 ...` — that means
   it's running. Leave this PowerShell window open.

3. Open your browser and go to:
   ```
   http://localhost:8000
   ```
   You should see the full live player table load.

4. When you're done, go back to the PowerShell window and press `Ctrl + C`
   to stop the server.

## Refreshing the data

Any time you want updated prices/points/form:
```
python fetch_fpl_data.py
```
Then just refresh the browser page (the server picks up the new file
automatically — no need to restart it).
