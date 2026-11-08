import tempfile,unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from foundry.preferences import Preferences
class FontPreferences(unittest.TestCase):
    def test_sizes_persist_without_replacing_theme_or_motion(self):
        with tempfile.TemporaryDirectory() as d:
            p=Preferences(Path(d)/'prefs.json');p.update({'theme':'dark','busy_motion':'paused'})
            for size in ('default','larger','large','extra-large','175','200'):
                p.update({'font_size':size});self.assertEqual(p.read()['font_size'],size)
                self.assertEqual(p.read()['theme'],'dark');self.assertEqual(p.read()['busy_motion'],'paused')
            with self.assertRaises(ValueError):p.update({'font_size':'huge-unbounded'})
