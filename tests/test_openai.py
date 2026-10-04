"""What the OpenAI-compatible backend asks a server for embeddings; needs no model,
only a server on this machine that answers like one."""

import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from elsewhere.adapters.backends import Settings, embed


class Embeddings(BaseHTTPRequestHandler):
    """Answers /v1/embeddings with each text's length as its vector, out of order,
    since the API does not promise the order of `data`."""

    requests: list = []

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Embeddings.requests.append((self.path, request))
        data = [{"object": "embedding", "index": index, "embedding": [float(len(text)), 1.0]}
                for index, text in enumerate(request["input"])]
        body = json.dumps({"object": "list", "model": request["model"],
                           "data": list(reversed(data)),
                           "usage": {"prompt_tokens": 1, "total_tokens": 1}}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *arguments):
        pass


class EmbedTest(unittest.TestCase):
    def setUp(self):
        Embeddings.requests = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Embeddings)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.settings = Settings(backend="openai", model="some-embedder",
                                 endpoint=f"http://127.0.0.1:{self.server.server_port}/v1",
                                 timeout=5.0)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def test_one_vector_per_text_in_the_order_asked(self):
        self.assertEqual(embed(["a", "abc"], self.settings), [[1.0, 1.0], [3.0, 1.0]])
        path, request = Embeddings.requests[0]
        self.assertEqual(path, "/v1/embeddings")
        self.assertEqual((request["model"], request["input"]), ("some-embedder", ["a", "abc"]))

    def test_a_server_that_cannot_be_reached_gives_no_vector(self):
        self.tearDown()
        self.assertEqual(embed(["a"], self.settings), [])
        self.setUp()


if __name__ == "__main__":
    unittest.main()
