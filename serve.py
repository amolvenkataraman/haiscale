#!/usr/bin/env python3
"""Local preview of ./site with UTF-8 declared on text files. Run: python3 serve.py [port]"""
import http.server
import sys
from functools import partial
from pathlib import Path


class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {
        **http.server.SimpleHTTPRequestHandler.extensions_map,
        ".txt": "text/plain; charset=utf-8",
        ".md": "text/markdown; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".svg": "image/svg+xml",
        ".woff2": "font/woff2",
    }


port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
site = Path(__file__).parent / "site"
print(f"Serving {site} at http://localhost:{port}")
http.server.ThreadingHTTPServer(("", port), partial(Handler, directory=str(site))).serve_forever()
