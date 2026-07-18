import unittest

from streamlit.testing.v1 import AppTest


class AppSmokeTests(unittest.TestCase):
    def test_default_app_renders_without_streamlit_errors(self):
        app = AppTest.from_file("app.py", default_timeout=30).run()
        self.assertEqual(list(app.exception), [])
        self.assertEqual(list(app.error), [])
        self.assertEqual(len(app.get("download_button")), 2)

    def test_sensitivity_panel_runs_and_reports_an_envelope(self):
        app = AppTest.from_file("app.py", default_timeout=120).run()
        button = next(b for b in app.get("button") if b.label == "run sensitivity")
        app = button.click().run()
        self.assertEqual(list(app.exception), [])
        self.assertEqual(list(app.error), [])
        envelope = app.get("table")[-1].value
        self.assertIn("q90 min°", envelope.columns)
        # the envelope must bracket the same-path baseline for every factor
        self.assertTrue(((envelope["q90 min°"].astype(float)
                          <= envelope["q90°"].astype(float))
                         & (envelope["q90°"].astype(float)
                            <= envelope["q90 max°"].astype(float))).all())

    def test_tie_cutoff_is_a_live_policy_knob(self):
        app = AppTest.from_file("app.py", default_timeout=120).run()
        markdown = " ".join(m.value for m in app.get("markdown"))
        self.assertIn("[tied]", markdown)          # f2/f3 swap ~6.5% at defaults
        self.assertIn("95% MC interval", markdown)
        cutoff = next(ni for ni in app.get("number_input") if "tie cutoff" in ni.label)
        app = cutoff.set_value(10.0).run()
        markdown = " ".join(m.value for m in app.get("markdown"))
        self.assertNotIn("[tied]", markdown)


if __name__ == "__main__":
    unittest.main()
