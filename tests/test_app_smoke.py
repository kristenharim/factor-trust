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

    def test_k_extremes_render(self):
        """k=1 has no factor pairs at all, so groups() is empty, the subspace dict
        is empty and the confusion heatmap must be skipped rather than drawn as a
        1x1 tile. k=4 is the other end of the sidebar's range."""
        for k in (1, 4):
            with self.subTest(k=k):
                app = AppTest.from_file("app.py", default_timeout=180).run()
                kin = next(ni for ni in app.get("number_input") if "k · factors" in ni.label)
                app = kin.set_value(k).run()
                self.assertEqual(list(app.exception), [], f"k={k}")
                self.assertEqual(list(app.error), [], f"k={k}")

    def test_spectrum_mode_refuses_an_empty_paste_then_renders_a_real_one(self):
        app = AppTest.from_file("app.py", default_timeout=180).run()
        app = app.get("radio")[0].set_value("sample spectrum").run()
        # switching modes with nothing pasted must stop with an explanation, not
        # a traceback and not a silently invented calibration
        self.assertEqual(list(app.exception), [])
        self.assertIn("requires exactly n=63", " ".join(e.value for e in app.error))

        # three spikes clear of a flat bulk: the shape from_spectrum expects
        spectrum = [40.0, 9.0, 4.0] + [1.0 + 0.01 * i for i in range(60)]
        area = next(t for t in app.get("text_area") if "eigenvalues" in t.label)
        app = area.set_value(" ".join(str(v) for v in spectrum)).run()
        self.assertEqual(list(app.exception), [])
        self.assertEqual(list(app.error), [])
        # the floor column must now come from the pasted eigenvalues, not the model
        self.assertIn("src=<i>spectrum</i>", " ".join(m.value for m in app.get("markdown")))

    def test_every_on_demand_panel_runs_clean(self):
        """The three heavy panels are behind buttons, so a smoke test that only
        loads the page never touches them. Click each one."""
        labels = ["how much of this depends on the return distribution?",
                  "and would more assets help?"]
        for label in labels:
            with self.subTest(panel=label):
                app = AppTest.from_file("app.py", default_timeout=300).run()
                button = next(b for b in app.get("button") if b.label == label)
                app = button.click().run()
                self.assertEqual(list(app.exception), [], label)
                self.assertEqual(list(app.error), [], label)

    def test_usability_bands_move_the_scorecard(self):
        """The bands are the reader's, so they have to actually rebind the verdict."""
        app = AppTest.from_file("app.py", default_timeout=180).run()
        green = next(ni for ni in app.get("number_input") if "usable below" in ni.label)
        app = green.set_value(89.0).run()
        markdown = " ".join(m.value for m in app.get("markdown"))
        # f1 does not tie with anything, so at a 89 degree green band it must read usable
        self.assertIn("a hedge on it clears", markdown)
        app = green.set_value(1.0).run()
        markdown = " ".join(m.value for m in app.get("markdown"))
        self.assertNotIn("a hedge on it clears", markdown)

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
