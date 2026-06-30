from pathlib import Path
import unittest


APP_ROOT = Path(__file__).resolve().parents[1]


class UserFacingBrandingTest(unittest.TestCase):
    def test_mail_subjects_and_notification_copy_use_workspace_brand(self):
        sources = "\n".join(
            (APP_ROOT / relative_path).read_text(encoding="utf-8")
            for relative_path in (
                "api.py",
                "notifications.py",
                "vecrm/doctype/vecrm_inquiry/vecrm_inquiry.py",
            )
        )

        legacy_copy = (
            "[VECRM Inquiry]",
            "VECRM Weekly Report",
            "VECRM: You have",
            "VECRM Admin:",
            "VECRM Email Pipeline Test",
            "the VECRM email pipeline",
            " in VECRM.",
        )
        for text in legacy_copy:
            with self.subTest(text=text):
                self.assertNotIn(text, sources)

        expected_copy = (
            "[Anusuya Workspace Inquiry]",
            "Anusuya Workspace Weekly Report",
            "Anusuya Workspace: You have",
            "Anusuya Workspace Admin:",
            "Anusuya Workspace Email Pipeline Test",
            "the Anusuya Workspace email pipeline",
            " in Anusuya Workspace.",
        )
        for text in expected_copy:
            with self.subTest(text=text):
                self.assertIn(text, sources)


if __name__ == "__main__":
    unittest.main()
