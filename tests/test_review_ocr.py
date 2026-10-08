import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from core.comic_ocr import crosscheck_ocr
from core.review_server import HTML_TEMPLATE, ReviewServerHandler


class ReviewOcrTest(unittest.TestCase):
    def test_two_engines_flag_missing_words_but_ignore_case(self):
        class Reader:
            def __call__(self, path):
                return [([], "Even the saintess must know I have no chance of living.", 0.9)], 0.1

        with patch("rapidocr_onnxruntime.RapidOCR", return_value=Reader()):
            from core import comic_ocr
            comic_ocr._SECONDARY_OCR = threading.local()
            _, flagged = crosscheck_ocr("panel.png", "EVEN THE SAINTESS MUST KNOW I HAVE NO CHANCE OF LIVING")
            self.assertFalse(flagged)
            _, flagged = crosscheck_ocr("panel.png", "Even the saintess must know")
            self.assertTrue(flagged)

    def test_review_accepts_corrected_text_and_flag(self):
        panel = {"file": "page_001_p01.png", "action": "INCLUDE", "ocr_text": "wrong",
                 "ocr_flagged": True, "ocr_ignore": False, "ocr_source": "first"}
        ReviewServerHandler.panels_data = [panel]
        ReviewServerHandler.submitted_result = None
        ReviewServerHandler.exit_event = threading.Event()
        server = ThreadingHTTPServer(("127.0.0.1", 0), ReviewServerHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port)
            edited = {**panel, "ocr_text": "correct words", "ocr_flagged": False, "ocr_source": "manual"}
            connection.request("POST", "/api/submit", json.dumps([edited]),
                               {"Content-Type": "application/json"})
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            response.read()
            self.assertEqual(ReviewServerHandler.submitted_result[0]["ocr_text"], "correct words")
            self.assertFalse(ReviewServerHandler.submitted_result[0]["ocr_flagged"])
            edited["ocr_ignore"] = True
            edited["ocr_source"] = "image_only"
            connection.request("POST", "/api/submit", json.dumps([edited]),
                               {"Content-Type": "application/json"})
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            response.read()
            self.assertTrue(ReviewServerHandler.submitted_result[0]["ocr_ignore"])
            connection.close()
        finally:
            server.shutdown()
            server.server_close()

    def test_page_has_ocr_review_controls(self):
        self.assertIn("OCR needs review", HTML_TEMPLATE)
        self.assertIn("editOcr", HTML_TEMPLATE)
        self.assertIn("Flag for image check", HTML_TEMPLATE)
        self.assertIn("Image only · ignore OCR", HTML_TEMPLATE)
