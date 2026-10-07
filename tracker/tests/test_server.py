"""HTTP server on a random port: state API, revision conflict, body limit, host and origin checks, static files, gap check."""
import http.client
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server  # noqa: E402
import store  # noqa: E402

HAS_NODE = shutil.which("node") is not None


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = store.Store(os.path.join(self.tmp.name, "applications.json"))
        self.httpd = server.TrackerServer(0, self.store)
        self.port = self.httpd.server_address[1]
        thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(self.httpd.shutdown)

    def request(self, method, path, body=None, headers=None, raw=None):
        """Sends the path as is (no client-side normalization); returns (status, headers, bytes)."""
        conn = http.client.HTTPConnection(server.HOST, self.port, timeout=30)
        self.addCleanup(conn.close)
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        sent = {"Content-Type": "application/json"} if data is not None else {}
        sent.update(headers or {})
        conn.request(method, path, body=data, headers=sent)
        res = conn.getresponse()
        return res.status, res.headers, res.read()

    def api(self, method, path, body=None, headers=None):
        status, _headers, data = self.request(method, path, body, headers)
        return status, json.loads(data)

    def card(self, **fields):
        base = {"id": "c1", "column": "applied", "company": "Example Corp",
                "history": [{"column": "applied", "date": "2026-09-01"}]}
        return {**base, **fields}

    def test_state_round_trip_and_conflict(self):
        status, body = self.api("GET", "/api/state")
        self.assertEqual(status, 200)
        self.assertEqual(body["dataPath"], self.store.path)
        loaded = body["document"]

        status, body = self.api("PUT", "/api/state", dict(loaded, cards=[self.card()]))
        self.assertEqual(status, 200)
        first = body["document"]
        self.assertNotEqual(first["updatedAt"], loaded["updatedAt"])

        status, body = self.api("PUT", "/api/state", dict(first, cards=[self.card(column="hr")]))
        self.assertEqual(status, 200)

        status, body = self.api("PUT", "/api/state", dict(first, cards=[]))
        self.assertEqual(status, 409)
        self.assertIn("reload", body["error"])
        self.assertEqual(self.api("GET", "/api/state")[1]["document"]["cards"][0]["column"], "hr")

    def test_invalid_document_is_400(self):
        status, body = self.api("PUT", "/api/state", {"cards": "nope"})
        self.assertEqual(status, 400)
        self.assertIn("invalid document", body["error"])
        status, _h, _d = self.request("PUT", "/api/state", raw=b"{not json")
        self.assertEqual(status, 400)

    def test_body_over_the_limit_is_413(self):
        conn = http.client.HTTPConnection(server.HOST, self.port, timeout=30)
        self.addCleanup(conn.close)
        conn.putrequest("PUT", "/api/state")
        conn.putheader("Content-Type", "application/json")
        conn.putheader("Content-Length", str(server.MAX_BODY + 1))
        conn.endheaders()
        self.assertEqual(conn.getresponse().status, 413)
        self.assertFalse(os.path.exists(self.store.path))

    def test_non_ascii_digit_length_is_411(self):
        conn = http.client.HTTPConnection(server.HOST, self.port, timeout=30)
        self.addCleanup(conn.close)
        conn.putrequest("PUT", "/api/state")
        conn.putheader("Content-Type", "application/json")
        conn.putheader("Content-Length", "\u00b2".encode("latin-1"))
        conn.endheaders()
        self.assertEqual(conn.getresponse().status, 411)

    def test_foreign_host_origin_and_content_type_are_refused(self):
        self.assertEqual(self.request("GET", "/api/state", headers={"Host": "evil.example:80"})[0], 403)
        doc = store.default_document()
        self.assertEqual(self.request("PUT", "/api/state", doc, {"Origin": "http://evil.example"})[0], 403)
        self.assertEqual(self.request("PUT", "/api/state", doc, {"Content-Type": "text/plain"})[0], 415)
        self.assertEqual(self.request("PUT", "/api/state", doc, {"Origin": f"http://127.0.0.1:{self.port}"})[0], 200)

    def test_index_is_served_with_a_csp(self):
        status, headers, data = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"<title>Application tracker</title>", data)
        self.assertIn("default-src 'self'", headers["Content-Security-Policy"])
        status, headers, _d = self.request("GET", "/app.js")
        self.assertEqual(status, 200)
        self.assertTrue(headers["Content-Type"].startswith("text/javascript"))

    def test_paths_outside_static_are_refused(self):
        for path in ["/../server.py", "/%2e%2e/server.py", "/..%2fserver.py", "/%2e%2e%2f%2e%2e%2fREADME.md",
                     "/static/../../store.py", "//etc/passwd", "/%2fetc%2fpasswd", "/../tests/test_server.py",
                     "/index.html%00.js", "/nope.html"]:
            with self.subTest(path):
                status, _h, data = self.request("GET", path)
                self.assertEqual(status, 404)
                self.assertNotIn(b"import", data)

    def test_unknown_api_route_is_404(self):
        self.assertEqual(self.api("GET", "/api/nope")[0], 404)
        self.assertEqual(self.api("POST", "/api/state", {})[0], 404)

    def test_gap_rejects_unknown_profile_and_bad_input(self):
        posting = "We need Kubernetes and Terraform."
        for body in [{"profile": "nobody", "variant": "main", "posting": posting},
                     {"profile": "../profiles/x", "variant": "main", "posting": posting},
                     {"profile": "_template", "variant": "main", "posting": posting},
                     {"profile": ["x"], "variant": "main", "posting": posting},
                     {"profile": "nobody", "variant": "main", "posting": "  "}]:
            with self.subTest(body["profile"]):
                status, data = self.api("POST", "/api/gap", body)
                self.assertEqual(status, 400)
                self.assertIn("error", data)
        self.assertEqual(self.api("POST", "/api/gap", ["not", "an", "object"])[0], 400)

    @unittest.skipUnless(HAS_NODE, "node is needed to read the profiles")
    def test_variants_have_ids_and_a_display_label(self):
        status, body = self.api("GET", "/api/variants")
        self.assertEqual(status, 200)
        self.assertEqual(body["errors"], [])
        for v in body["variants"]:
            self.assertEqual(set(v), {"profile", "variant", "label"})
            self.assertTrue(v["profile"] and v["variant"] and v["label"].strip(), v)
            self.assertNotIn("undefined", v["label"])

    @unittest.skipUnless(HAS_NODE, "node is needed to read the profiles")
    def test_variant_label_falls_back_to_the_headline_and_names_the_profile(self):
        root = os.path.join(self.tmp.name, "repo")
        shutil.copytree(os.path.join(server.ROOT, "profiles", "_template"), os.path.join(root, "profiles", "alex"))
        shutil.copytree(os.path.join(server.ROOT, "profiles", "_template"), os.path.join(root, "profiles", "sam"))
        shutil.copytree(os.path.join(server.ROOT, "themes"), os.path.join(root, "themes"))
        shutil.copy(os.path.join(server.ROOT, "read-profile.js"), root)
        with open(os.path.join(root, "profiles", "sam", "content.js"), encoding="utf-8") as f:
            text = f.read().replace("main: {", 'main: {\n      label: "Backend",', 1)
        with open(os.path.join(root, "profiles", "sam", "content.js"), "w", encoding="utf-8") as f:
            f.write(text)
        variants, errors = server.list_variants(root)
        self.assertEqual(errors, [])
        self.assertEqual([v["label"] for v in variants], ["Backend Engineer (alex)", "Backend (sam)"])

    @unittest.skipUnless(HAS_NODE, "node is needed to read the profiles")
    def test_gap_rejects_an_unknown_variant_and_runs_a_known_one(self):
        status, body = self.api("GET", "/api/variants")
        self.assertEqual(status, 200)
        if not body["variants"]:
            self.skipTest("no profile besides _template")
        variant = body["variants"][0]
        profile = {"id": variant["profile"]}
        variant = {"id": variant["variant"]}
        status, data = self.api("POST", "/api/gap", {"profile": profile["id"], "variant": "--help",
                                                     "posting": "Kubernetes"})
        self.assertEqual(status, 400)
        self.assertIn("unknown variant", data["error"])
        status, data = self.api("POST", "/api/gap", {"profile": profile["id"], "variant": variant["id"],
                                                     "posting": "Required: Kubernetes, Terraform and Rust."})
        self.assertEqual(status, 200, data)
        self.assertIn("Match score", data["output"])


if __name__ == "__main__":
    unittest.main()
